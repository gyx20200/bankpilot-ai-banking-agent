package com.bankpilot.demo;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.server.ResponseStatusException;

/** Tests actual Spring Security and SQL mutation against H2 (not mock Java business logic). */
@SpringBootTest
@AutoConfigureMockMvc
@Sql(scripts="/subscription-test-schema.sql", executionPhase=Sql.ExecutionPhase.BEFORE_TEST_CLASS)
class SubscriptionCancellationTest {
    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
    @Autowired ObjectMapper mapper;
    @Autowired SubscriptionCancellationService service;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM subscription_cancel_events");
        jdbc.update("DELETE FROM subscription_cancel_orders");
        jdbc.update("UPDATE subscriptions SET status='ACTIVE',cancelled_at=NULL,next_pay_date=DATE '2026-11-08' WHERE id=1");
        jdbc.update("UPDATE subscriptions SET status='ACTIVE',cancelled_at=NULL,next_pay_date=DATE '2026-11-12' WHERE id=2");
    }

    private String auth() throws Exception {
        String json = mapper.writeValueAsString(Map.of("username","demo", "password","JUnitDemoPassword2026!"));
        String login = mvc.perform(post("/api/auth/demo-login").contentType(MediaType.APPLICATION_JSON).content(json))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        return "Bearer " + mapper.readTree(login).get("token").asText();
    }

    private JsonNode prepare(String token, String requestId, int subscriptionId, String runId) throws Exception {
        String body = mapper.writeValueAsString(Map.of("subscriptionId",subscriptionId,"requestId",requestId,"workflowId",runId));
        String raw = mvc.perform(post("/api/subscription-cancellations/prepare")
            .header("Authorization",token).contentType(MediaType.APPLICATION_JSON).content(body))
            .andExpect(status().isCreated()).andReturn().getResponse().getContentAsString();
        return mapper.readTree(raw);
    }

    @Test void noAnonymousAccess() throws Exception {
        mvc.perform(post("/api/subscription-cancellations/prepare").contentType(MediaType.APPLICATION_JSON)
            .content("{\"subscriptionId\":1,\"requestId\":\"day6-unauth-01\"}"))
            .andExpect(status().isUnauthorized());
        mvc.perform(get("/api/subscription-cancellations/1")).andExpect(status().isUnauthorized());
        mvc.perform(post("/api/subscription-cancellations/1/execute")).andExpect(status().isUnauthorized());
    }

    @Test void prepareOnlyNoMutationAndIdempotency() throws Exception {
        String a = auth();
        BigDecimal balance = jdbc.queryForObject("SELECT balance FROM accounts WHERE id=1", BigDecimal.class);
        int txCount = jdbc.queryForObject("SELECT COUNT(*) FROM transactions", Integer.class);
        JsonNode first = prepare(a,"day6-prep-00001",1,"day6-run-00001");
        JsonNode again = prepare(a,"day6-prep-00001",1,"day6-run-00001");
        assertThat(first.get("orderId").asLong()).isEqualTo(again.get("orderId").asLong());
        assertThat(first.get("status").asText()).isEqualTo("PENDING_APPROVAL");
        assertThat(first.get("riskLevel").asText()).isEqualTo("YELLOW");
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM subscription_cancel_orders",Integer.class)).isEqualTo(1);
        assertThat(jdbc.queryForObject("SELECT status FROM subscriptions WHERE id=1",String.class)).isEqualTo("ACTIVE");
        assertThat(jdbc.queryForObject("SELECT balance FROM accounts WHERE id=1",BigDecimal.class)).isEqualByComparingTo(balance);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM transactions",Integer.class)).isEqualTo(txCount);
    }

    @Test void cannotReUseKeyForOtherSubscription() throws Exception {
        String a=auth(); prepare(a,"day6-samekey01",1,"day6-run-00001");
        mvc.perform(post("/api/subscription-cancellations/prepare").header("Authorization",a)
            .contentType(MediaType.APPLICATION_JSON).content("""
                {"subscriptionId":2,"requestId":"day6-samekey01","workflowId":"day6-run-00001"}
                """)).andExpect(status().isConflict());
    }

    @Test void rejectsOtherUsersSubscription() throws Exception {
        String a=auth();
        mvc.perform(post("/api/subscription-cancellations/prepare").header("Authorization",a)
            .contentType(MediaType.APPLICATION_JSON).content("""
                {"subscriptionId":3,"requestId":"day6-other-user","workflowId":"day6-run-00001"}
                """)).andExpect(status().isNotFound());
    }

    @Test void requiresExplicitAuthorization() throws Exception {
        String a=auth(); long id=prepare(a,"day6-noauth-001",1,"day6-run-00001").get("orderId").asLong();
        mvc.perform(post("/api/subscription-cancellations/"+id+"/execute")
            .header("Authorization",a)).andExpect(status().isConflict());
        assertThat(jdbc.queryForObject("SELECT status FROM subscriptions WHERE id=1",String.class)).isEqualTo("ACTIVE");
    }

    @Test void declinePreventsExecution() throws Exception {
        String a=auth(); long id=prepare(a,"day6-decline-01",1,"day6-run-00001").get("orderId").asLong();
        mvc.perform(post("/api/subscription-cancellations/"+id+"/authorize").header("Authorization",a)
            .contentType(MediaType.APPLICATION_JSON).content("{\"confirmed\":false}"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("CANCELLED"));
        mvc.perform(post("/api/subscription-cancellations/"+id+"/execute")
            .header("Authorization",a)).andExpect(status().isConflict());
        assertThat(jdbc.queryForObject("SELECT status FROM subscriptions WHERE id=1",String.class)).isEqualTo("ACTIVE");
    }

    @Test void approveExecuteRepeatedExecuteIsSafe() throws Exception {
        String a=auth(); long id=prepare(a,"day6-success-01",1,"day6-run-00001").get("orderId").asLong();
        BigDecimal balanceBefore=jdbc.queryForObject("SELECT balance FROM accounts WHERE id=1",BigDecimal.class);
        int txBefore=jdbc.queryForObject("SELECT COUNT(*) FROM transactions",Integer.class);
        mvc.perform(post("/api/subscription-cancellations/"+id+"/authorize").header("Authorization",a)
            .contentType(MediaType.APPLICATION_JSON).content("{\"confirmed\":true}"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("AUTHORIZED"));
        assertThat(jdbc.queryForObject("SELECT status FROM subscriptions WHERE id=1",String.class)).isEqualTo("ACTIVE");
        for (int i=0;i<2;i++) mvc.perform(post("/api/subscription-cancellations/"+id+"/execute")
            .header("Authorization",a)).andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("SUCCESS"));
        mvc.perform(get("/api/subscription-cancellations/"+id).header("Authorization",a))
            .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("SUCCESS"));
        assertThat(jdbc.queryForObject("SELECT status FROM subscriptions WHERE id=1",String.class)).isEqualTo("CANCELLED");
        assertThat(jdbc.queryForObject("SELECT next_pay_date FROM subscriptions WHERE id=1",java.sql.Date.class)).isNull();
        assertThat(jdbc.queryForObject("SELECT status FROM subscriptions WHERE id=2",String.class)).isEqualTo("ACTIVE");
        assertThat(jdbc.queryForObject("SELECT balance FROM accounts WHERE id=1",BigDecimal.class)).isEqualByComparingTo(balanceBefore);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM transactions",Integer.class)).isEqualTo(txBefore);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM subscription_cancel_events WHERE order_id=? AND action='EXECUTE'",Integer.class,id)).isEqualTo(1);
    }

    @Test void secondLiveRequestForSameSubscriptionConflicts() throws Exception {
        String a=auth(); prepare(a,"day6-duplicate-01",1,"day6-run-00001");
        mvc.perform(post("/api/subscription-cancellations/prepare").header("Authorization",a)
            .contentType(MediaType.APPLICATION_JSON).content("""
                {"subscriptionId":1,"requestId":"day6-duplicate-02","workflowId":"day6-run-00001"}
                """)).andExpect(status().isConflict());
    }

    @Test void expiredOrderCannotBeAuthorizedAndNewRequestCanBePrepared() throws Exception {
        String a=auth(); long id=prepare(a,"day6-expired-01",1,"day6-run-00001").get("orderId").asLong();
        jdbc.update("UPDATE subscription_cancel_orders SET expires_at=? WHERE id=?",
            java.sql.Timestamp.valueOf("2001-01-01 00:00:00"),id);
        mvc.perform(post("/api/subscription-cancellations/"+id+"/authorize").header("Authorization",a)
            .contentType(MediaType.APPLICATION_JSON).content("{\"confirmed\":true}"))
            .andExpect(status().isConflict());
        mvc.perform(post("/api/subscription-cancellations/"+id+"/execute")
            .header("Authorization",a)).andExpect(status().isConflict());
        JsonNode newer=prepare(a,"day6-expired-02",1,"day6-run-00001");
        assertThat(newer.get("orderId").asLong()).isNotEqualTo(id);
    }

    @Test void wrongOwnerCannotReadOrApprove() throws Exception {
        String a=auth(); long id=prepare(a,"day6-owner-0001",1,"day6-run-00001").get("orderId").asLong();
        assertThrows(ResponseStatusException.class, () -> service.status(2,id));
        assertThrows(ResponseStatusException.class, () -> service.authorize(2,id,true));
    }

    @Test void badRequestValidation() throws Exception {
        String a=auth();
        for (String payload: new String[] {
            "{\"subscriptionId\":0,\"requestId\":\"day6-validation\"}",
            "{\"subscriptionId\":1,\"requestId\":\"short\"}",
            "{\"subscriptionId\":1,\"requestId\":\"day6-valid-id\",\"workflowId\":\"../../bad\"}"
        }) {
            mvc.perform(post("/api/subscription-cancellations/prepare").header("Authorization",a)
              .contentType(MediaType.APPLICATION_JSON).content(payload))
              .andExpect(status().isBadRequest());
        }
    }
}
