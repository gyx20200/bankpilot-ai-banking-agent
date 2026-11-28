package com.bankpilot.demo;

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
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties={"spring.datasource.url=jdbc:h2:mem:bankpilotcardsd14;DB_CLOSE_DELAY=-1"})
@AutoConfigureMockMvc
@Sql(scripts="classpath:d14_cards_h2.sql",executionPhase=Sql.ExecutionPhase.BEFORE_TEST_METHOD)
class DemoCardFlowTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired JdbcTemplate jdbc;
    @Autowired DemoCardService service;
    @BeforeEach void clean() {
        jdbc.update("DELETE FROM demo_card_limit_events");
        jdbc.update("DELETE FROM demo_card_applications");
        jdbc.update("DELETE FROM demo_virtual_cards");
    }
    String token() throws Exception {
        String raw=mvc.perform(post("/api/auth/demo-login")
             .contentType(MediaType.APPLICATION_JSON)
             .content(json.writeValueAsString(Map.of("username","demo","password","JUnitDemoPassword2026!"))))
             .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        return "Bearer "+json.readTree(raw).get("token").asText();
    }
    JsonNode send(String path,String t,Object body) throws Exception {
        String raw=mvc.perform(post(path).header("Authorization",t)
              .contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(body)))
              .andExpect(status().is2xxSuccessful()).andReturn().getResponse().getContentAsString();
        return json.readTree(raw);
    }
    long prepare(String token,String rid) throws Exception {
        return send("/api/demo/cards/applications/prepare",token,
              Map.of("cardType","VIRTUAL_DEBIT","requestId",rid)).get("applicationId").asLong();
    }
    long issue(String token,String rid) throws Exception {
        long id=prepare(token,rid);
        assertThat(send("/api/demo/cards/applications/"+id+"/confirm",token,Map.of("confirmed",true))
            .get("status").asText()).isEqualTo("ISSUED");
        return id;
    }
    @Test void unauthenticatedUsersCannotListOrIssueCards() throws Exception {
        mvc.perform(get("/api/demo/cards")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/demo/cards/applications")).andExpect(status().isUnauthorized());
        mvc.perform(post("/api/demo/cards/applications/prepare")
            .contentType(MediaType.APPLICATION_JSON).content("{}"))
            .andExpect(status().isUnauthorized());
    }
    @Test void preparationDoesNotIssueAndDuplicateKeyReturnsSameApplication() throws Exception {
        String t=token(); long id=prepare(t,"d14-safe-key-0001");
        assertThat(prepare(t,"d14-safe-key-0001")).isEqualTo(id);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_virtual_cards",Long.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_card_applications",Long.class)).isEqualTo(1);
        assertThat(service.application(1,id).status()).isEqualTo("PENDING_APPROVAL");
    }
    @Test void explicitConfirmIssuesAliasOnceAndDoesNotTouchBankBalance() throws Exception {
        String t=token();
        BigDecimal before=jdbc.queryForObject("SELECT balance FROM accounts WHERE id=1",BigDecimal.class);
        long id=issue(t,"d14-safe-key-0002");
        assertThat(send("/api/demo/cards/applications/"+id+"/confirm",t,Map.of("confirmed",true))
            .get("status").asText()).isEqualTo("ISSUED");
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_virtual_cards",Long.class)).isEqualTo(1);
        assertThat(jdbc.queryForObject("SELECT balance FROM accounts WHERE id=1",BigDecimal.class)).isEqualByComparingTo(before);
        var card=service.cards(1).get(0);
        assertThat(card.cardAlias()).startsWith("BP-VC-");
        assertThat(card.cardAlias()).doesNotContain("****");
        assertThat(card.singleTransactionLimit()).isEqualByComparingTo("1000.00");
    }
    @Test void rejectionCreatesNoCard() throws Exception {
        String t=token();long id=prepare(t,"d14-safe-key-0003");
        assertThat(send("/api/demo/cards/applications/"+id+"/confirm",t,Map.of("confirmed",false))
            .get("status").asText()).isEqualTo("CANCELLED");
        assertThat(service.cards(1)).isEmpty();
    }
    @Test void limitMayOnlyBeNarrowedAndRepeatedRequestHasNoSideEffect() throws Exception {
        String t=token();issue(t,"d14-safe-key-0004");
        long cid=service.cards(1).get(0).cardId();
        var payload=Map.of("singleTransactionLimit","300.00","disableOnline",true,"requestId","d14-limit-0004");
        assertThat(new java.math.BigDecimal(
            send("/api/demo/cards/"+cid+"/restrictions",t,payload)
                .get("singleTransactionLimit").asText()
        )).isEqualByComparingTo("300.00");
        send("/api/demo/cards/"+cid+"/restrictions",t,payload);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM demo_card_limit_events",Long.class)).isEqualTo(1);
        assertThat(service.cards(1).get(0).onlineEnabled()).isFalse();
        mvc.perform(post("/api/demo/cards/"+cid+"/restrictions")
            .header("Authorization",t).contentType(MediaType.APPLICATION_JSON)
            .content(json.writeValueAsString(Map.of("singleTransactionLimit","800.00",
                 "disableOnline",false,"requestId","d14-increase-0004"))))
            .andExpect(status().isConflict());
    }
    @Test void requestIdWithChangedRestrictionIsRejected() throws Exception {
        String t=token();issue(t,"d14-safe-key-0005");long cid=service.cards(1).get(0).cardId();
        send("/api/demo/cards/"+cid+"/restrictions",t,
            Map.of("singleTransactionLimit","200.00","disableOnline",false,"requestId","d14-limit-0005"));
        mvc.perform(post("/api/demo/cards/"+cid+"/restrictions")
            .header("Authorization",t).contentType(MediaType.APPLICATION_JSON)
            .content(json.writeValueAsString(Map.of("singleTransactionLimit","100.00",
                 "disableOnline",false,"requestId","d14-limit-0005"))))
            .andExpect(status().isConflict());
    }
    @Test void directServiceReadAndConfirmRejectForeignOwner() throws Exception {
        String t=token();long aid=issue(t,"d14-safe-key-0006");
        assertThat(service.cards(2)).isEmpty();
        assertThat(service.applications(2)).isEmpty();
        assertThatThrownBy(()->service.application(2,aid))
            .isInstanceOf(org.springframework.web.server.ResponseStatusException.class);
        assertThatThrownBy(()->service.confirm(2,aid,true))
            .isInstanceOf(org.springframework.web.server.ResponseStatusException.class);
    }
}
