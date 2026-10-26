package com.bankpilot.demo;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.math.BigDecimal;
import java.util.Map;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class TransferWorkflowSecurityTest {
    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
    @Autowired ObjectMapper mapper;

    @BeforeEach
    void resetIsolatedH2Demo() {
        jdbc.update("DELETE FROM audit_events");
        jdbc.update("DELETE FROM transactions WHERE transfer_order_id IS NOT NULL");
        jdbc.update("DELETE FROM approval_records");
        jdbc.update("DELETE FROM transfer_orders");
        jdbc.update("UPDATE accounts SET balance=12580.50 WHERE id=1");
        jdbc.update("UPDATE accounts SET balance=5000.00 WHERE id=2");
    }

    String token() throws Exception {
        var body = mapper.writeValueAsString(Map.of("username","demo","password","JUnitDemoPassword2026!"));
        String raw = mvc.perform(post("/api/auth/demo-login").contentType(MediaType.APPLICATION_JSON).content(body))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        return "Bearer " + mapper.readTree(raw).get("token").asText();
    }

    JsonNode postJson(String path, String token, Object body) throws Exception {
        var req = post(path).contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(body));
        if (token != null) req.header("Authorization",token);
        String raw = mvc.perform(req).andExpect(status().is2xxSuccessful()).andReturn().getResponse().getContentAsString();
        return mapper.readTree(raw);
    }

    JsonNode create(String token, String amount, String key) throws Exception {
        return postJson("/api/transfers/prepare",token,
            Map.of("payeeId",1,"amount",amount,"requestId",key,"remark","Day4"));
    }

    JsonNode authorize(String token, long id, boolean confirmed, String otp) throws Exception {
        return postJson("/api/transfers/"+id+"/authorize",token,
            Map.of("confirmed",confirmed,"otp",otp == null ? "" : otp));
    }

    JsonNode execute(String token, long id) throws Exception {
        return postJson("/api/transfers/"+id+"/execute",token,Map.of());
    }

    BigDecimal balance(long id) { return jdbc.queryForObject("SELECT balance FROM accounts WHERE id=?",BigDecimal.class,id); }
    long rowCount(long id) { return jdbc.queryForObject("SELECT COUNT(*) FROM transactions WHERE transfer_order_id=?",Long.class,id); }

    @Test
    void yellowConfirmationExecutesAtomicallyAndWritesTwoLegsAndAudit() throws Exception {
        String t=token(); long id=create(t,"200.00","day4-yellow-001").get("orderId").asLong();
        assertThat(balance(1)).isEqualByComparingTo("12580.50");
        mvc.perform(post("/api/transfers/"+id+"/execute").header("Authorization",t))
            .andExpect(status().isConflict());
        assertThat(authorize(t,id,true,null).get("status").asText()).isEqualTo("AUTHORIZED");
        assertThat(execute(t,id).get("status").asText()).isEqualTo("SUCCESS");
        assertThat(balance(1)).isEqualByComparingTo("12380.50");
        assertThat(balance(2)).isEqualByComparingTo("5200.00");
        assertThat(rowCount(id)).isEqualTo(2);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM audit_events WHERE order_id=? AND result='SUCCESS'",Long.class,id)).isEqualTo(1);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM transactions WHERE transfer_order_id=? AND direction='IN'",Long.class,id)).isEqualTo(1);
    }

    @Test
    void duplicateExecutionDoesNotDebitAgain() throws Exception {
        String t=token();long id=create(t,"100.00","day4-idem-001").get("orderId").asLong();
        authorize(t,id,true,null);
        execute(t,id);
        BigDecimal after=balance(1);
        assertThat(execute(t,id).get("status").asText()).isEqualTo("SUCCESS");
        assertThat(balance(1)).isEqualByComparingTo(after);
        assertThat(rowCount(id)).isEqualTo(2);
    }

    @Test
    void cancellationNeverChangesBalances() throws Exception {
        String t=token();long id=create(t,"100.00","day4-cancel-001").get("orderId").asLong();
        assertThat(authorize(t,id,false,null).get("status").asText()).isEqualTo("CANCELLED");
        mvc.perform(post("/api/transfers/"+id+"/execute").header("Authorization",t)).andExpect(status().isConflict());
        assertThat(balance(1)).isEqualByComparingTo("12580.50");
        assertThat(rowCount(id)).isZero();
    }

    @Test
    void redOtpValidatesAndExecutes() throws Exception {
        String t=token();long id=create(t,"1500.00","day4-red-0001").get("orderId").asLong();
        assertThat(postJson("/api/transfers/"+id+"/otp/request",t,Map.of()).get("result").asText()).isEqualTo("OTP_ISSUED");
        String debug=mvc.perform(get("/api/transfers/"+id+"/demo-otp").header("Authorization",t))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        String code=mapper.readTree(debug).get("otp").asText();
        assertThat(code).hasSize(6);
        assertThat(authorize(t,id,true,code).get("status").asText()).isEqualTo("AUTHORIZED");
        assertThat(execute(t,id).get("status").asText()).isEqualTo("SUCCESS");
        assertThat(balance(1)).isEqualByComparingTo("11080.50");
        assertThat(balance(2)).isEqualByComparingTo("6500.00");
        assertThat(rowCount(id)).isEqualTo(2);
        mvc.perform(get("/api/transfers/"+id+"/demo-otp").header("Authorization",t)).andExpect(status().isNotFound());
    }

    @Test
    void invalidOtpFiveTimesCancelsOrderAndLocksExecution() throws Exception {
        String t=token();long id=create(t,"1500.00","day4-otp-lock1").get("orderId").asLong();
        postJson("/api/transfers/"+id+"/otp/request",t,Map.of());
        String code=mapper.readTree(mvc.perform(get("/api/transfers/"+id+"/demo-otp")
            .header("Authorization",t)).andReturn().getResponse().getContentAsString()).get("otp").asText();
        String wrong="000000".equals(code)?"999999":"000000";
        for (int i=1;i<=5;i++) {
            JsonNode r=authorize(t,id,true,wrong);
            assertThat(r.get("result").asText()).isEqualTo(i==5?"TOO_MANY_FAILURES":"INVALID_OTP");
            assertThat(r.get("remainingAttempts").asInt()).isEqualTo(5-i);
        }
        assertThat(balance(1)).isEqualByComparingTo("12580.50");
        assertThat(rowCount(id)).isZero();
        mvc.perform(post("/api/transfers/"+id+"/execute").header("Authorization",t)).andExpect(status().isConflict());
    }

    @Test
    void pending500ForcesEarlier800ToUpgradeBeforeAuthorize() throws Exception {
        String t=token(); long a=create(t,"800.00","day4-risk-800").get("orderId").asLong();
        JsonNode b=create(t,"500.00","day4-risk-500");
        assertThat(b.get("riskLevel").asText()).isEqualTo("RED");
        JsonNode recheck=authorize(t,a,true,null);
        assertThat(recheck.get("result").asText()).isEqualTo("RISK_UPGRADED_OTP_REQUIRED");
        assertThat(recheck.get("status").asText()).isEqualTo("PENDING_APPROVAL");
        mvc.perform(post("/api/transfers/"+a+"/execute").header("Authorization",t)).andExpect(status().isConflict());
        assertThat(balance(1)).isEqualByComparingTo("12580.50");
    }

    @Test
    void expiredAuthorizationMustNotExecute() throws Exception {
        String t=token();long id=create(t,"200.00","day4-expired1").get("orderId").asLong();
        authorize(t,id,true,null);
        jdbc.update("UPDATE approval_records SET expires_at=TIMESTAMP '2020-01-01 00:00:00' WHERE order_id=?",id);
        JsonNode r=execute(t,id);
        assertThat(r.get("status").asText()).isEqualTo("PENDING_APPROVAL");
        assertThat(balance(1)).isEqualByComparingTo("12580.50");
        assertThat(rowCount(id)).isZero();
    }

    @Test
    void insufficientFundsAtExecutionFailsWithoutEntries() throws Exception {
        String t=token();long id=create(t,"200.00","day4-balance1").get("orderId").asLong();
        authorize(t,id,true,null);
        jdbc.update("UPDATE accounts SET balance=10.00 WHERE id=1");
        JsonNode result=execute(t,id);
        assertThat(result.get("status").asText()).isEqualTo("FAILED");
        assertThat(balance(1)).isEqualByComparingTo("10.00");
        assertThat(balance(2)).isEqualByComparingTo("5000.00");
        assertThat(rowCount(id)).isZero();
    }

    @Test
    void unauthenticatedApprovalExecuteAndForeignOrderAreDenied() throws Exception {
        String t=token();long id=create(t,"200.00","day4-auth-0001").get("orderId").asLong();
        mvc.perform(post("/api/transfers/"+id+"/authorize")
            .contentType(MediaType.APPLICATION_JSON).content("{\"confirmed\":true}"))
            .andExpect(status().isUnauthorized());
        mvc.perform(post("/api/transfers/"+id+"/execute"))
            .andExpect(status().isUnauthorized());
        mvc.perform(get("/api/transfers/99999999").header("Authorization",t))
            .andExpect(status().isNotFound());
        assertThat(balance(1)).isEqualByComparingTo("12580.50");
    }
}
