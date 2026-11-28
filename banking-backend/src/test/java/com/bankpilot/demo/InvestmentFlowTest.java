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
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties={"spring.datasource.url=jdbc:h2:mem:bankpilotinvestmentd13;DB_CLOSE_DELAY=-1"})
@AutoConfigureMockMvc
@Sql(scripts="classpath:d13_investments_h2.sql",executionPhase=Sql.ExecutionPhase.BEFORE_TEST_METHOD)
class InvestmentFlowTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM investment_ledger");
        jdbc.update("DELETE FROM investment_positions");
        jdbc.update("DELETE FROM investment_orders");
        jdbc.update("DELETE FROM investment_profiles");
        jdbc.update("UPDATE accounts SET balance=12580.50 WHERE id=1");
    }
    String token() throws Exception {
        String body=json.writeValueAsString(Map.of("username","demo","password","JUnitDemoPassword2026!"));
        String raw=mvc.perform(post("/api/auth/demo-login").contentType(MediaType.APPLICATION_JSON).content(body))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        return "Bearer " + json.readTree(raw).get("token").asText();
    }
    JsonNode send(String path, String token, Map<String,?> data) throws Exception {
        var request=post(path).header("Authorization",token).contentType(MediaType.APPLICATION_JSON)
            .content(json.writeValueAsString(data));
        return json.readTree(mvc.perform(request).andExpect(status().is2xxSuccessful())
            .andReturn().getResponse().getContentAsString());
    }
    void assess(String bearer,int level) throws Exception {
        send("/api/demo/investments/profile/assess",bearer,
            Map.of("lossTolerance",level,"horizon",level,"experience",level));
    }
    long prepare(String bearer,long pid,String action,String units,String key) throws Exception {
        return send("/api/demo/investments/orders/prepare",bearer,
            Map.of("productId",pid,"action",action,"units",units,"requestId",key))
            .get("orderId").asLong();
    }
    String confirm(String bearer,long orderId,boolean confirmed) throws Exception {
        return send("/api/demo/investments/orders/"+orderId+"/confirm",bearer,
            Map.of("confirmed",confirmed)).get("status").asText();
    }
    BigDecimal balance() { return jdbc.queryForObject("SELECT balance FROM accounts WHERE id=1",BigDecimal.class); }
    long ledger() { return jdbc.queryForObject("SELECT COUNT(*) FROM investment_ledger",Long.class); }
    BigDecimal holding() { return jdbc.queryForObject(
        "SELECT units FROM investment_positions WHERE user_id=1 AND product_id=101",BigDecimal.class); }

    @Test void onlyAuthenticatedUserCanAccessProductsAndOrders() throws Exception {
        mvc.perform(get("/api/demo/investments/products")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/demo/investments/orders/1")).andExpect(status().isUnauthorized());
        String t=token();
        mvc.perform(get("/api/demo/investments/products").header("Authorization",t))
            .andExpect(status().isOk());
    }

    @Test void prepareDoesNotMoveFundsThenApproveDoesAndDoubleApproveIsIdempotent() throws Exception {
        String t=token(); assess(t,1);
        long oid=prepare(t,101,"BUY","10","d13-buy-00001");
        assertThat(balance()).isEqualByComparingTo("12580.50");
        assertThat(ledger()).isZero();
        assertThat(prepare(t,101,"BUY","10.00","d13-buy-00001")).isEqualTo(oid);
        assertThat(confirm(t,oid,true)).isEqualTo("SUCCESS");
        assertThat(balance()).isEqualByComparingTo("11580.50");
        assertThat(holding()).isEqualByComparingTo("10.00");
        assertThat(ledger()).isEqualTo(1);
        assertThat(confirm(t,oid,true)).isEqualTo("SUCCESS");
        assertThat(balance()).isEqualByComparingTo("11580.50");
        assertThat(ledger()).isEqualTo(1);
    }

    @Test void redeemReturnsCashExactlyOnceAndDecreasesPosition() throws Exception {
        String t=token(); assess(t,1);
        long buy=prepare(t,101,"BUY","10","d13-buy-00002");
        confirm(t,buy,true);
        long sell=prepare(t,101,"REDEEM","3","d13-red-00002");
        assertThat(confirm(t,sell,true)).isEqualTo("SUCCESS");
        assertThat(balance()).isEqualByComparingTo("11880.50");
        assertThat(holding()).isEqualByComparingTo("7.00");
        assertThat(ledger()).isEqualTo(2);
        assertThat(confirm(t,sell,true)).isEqualTo("SUCCESS");
        assertThat(ledger()).isEqualTo(2);
    }

    @Test void rejectionDoesNotMoveFundsOrUnits() throws Exception {
        String t=token(); assess(t,1);
        long oid=prepare(t,101,"BUY","5","d13-buy-cancel");
        assertThat(confirm(t,oid,false)).isEqualTo("CANCELLED");
        assertThat(balance()).isEqualByComparingTo("12580.50");
        assertThat(ledger()).isZero();
    }

    @Test void suitabilityRejectsHighRiskProduct() throws Exception {
        String t=token(); assess(t,1);
        mvc.perform(post("/api/demo/investments/orders/prepare")
                .header("Authorization",t).contentType(MediaType.APPLICATION_JSON)
                .content(json.writeValueAsString(Map.of("productId",103,"action","BUY",
                    "units","1","requestId","d13-too-risky"))))
            .andExpect(status().isConflict());
        assertThat(ledger()).isZero();
    }

    @Test void insufficientBalanceDoesNotCreateHoldingOrLedger() throws Exception {
        String t=token(); assess(t,1);
        long oid=prepare(t,101,"BUY","10","d13-funds-0001");
        jdbc.update("UPDATE accounts SET balance=10.00 WHERE id=1");
        assertThat(confirm(t,oid,true)).isEqualTo("FAILED");
        assertThat(balance()).isEqualByComparingTo("10.00");
        assertThat(ledger()).isZero();
    }

    @Test void noExistingUnitsCannotBeRedeemed() throws Exception {
        String t=token();
        long oid=prepare(t,101,"REDEEM","5","d13-no-holdings");
        assertThat(confirm(t,oid,true)).isEqualTo("FAILED");
        assertThat(balance()).isEqualByComparingTo("12580.50");
        assertThat(ledger()).isZero();
    }

    @Test void otherUserIdCannotReadOrder() throws Exception {
        String t=token(); assess(t,1);
        long oid=prepare(t,101,"BUY","1","d13-owner-0001");
        var service = new InvestmentService(jdbc);
        org.assertj.core.api.Assertions.assertThatThrownBy(() -> service.getOrder(2,oid))
            .isInstanceOf(org.springframework.web.server.ResponseStatusException.class);
    }

    @Test void changedIdempotencyPayloadRejected() throws Exception {
        String t=token(); assess(t,1);
        prepare(t,101,"BUY","2","d13-same-key");
        mvc.perform(post("/api/demo/investments/orders/prepare")
                .header("Authorization",t).contentType(MediaType.APPLICATION_JSON)
                .content(json.writeValueAsString(Map.of("productId",101,"action","BUY",
                    "units","3","requestId","d13-same-key"))))
            .andExpect(status().isConflict());
    }
}
