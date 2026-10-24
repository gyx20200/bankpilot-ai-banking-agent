
package com.bankpilot.demo;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

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
class TransferPrepareSecurityTest {

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
    @Autowired ObjectMapper mapper;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM approval_records");
        jdbc.update("DELETE FROM transfer_orders");
    }

    private String token() throws Exception {
        String json = mapper.writeValueAsString(
            Map.of(
                "username", "demo",
                "password", "JUnitDemoPassword2026!"
            )
        );

        String response = mvc.perform(
            post("/api/auth/demo-login")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json)
        )
        .andExpect(status().isOk())
        .andReturn()
        .getResponse()
        .getContentAsString();

        return mapper.readTree(response).get("token").asText();
    }

    private JsonNode order(
        String bearer,
        String requestId,
        String amount,
        int payeeId,
        String remark
    ) throws Exception {

        String body = mapper.writeValueAsString(
            Map.of(
                "payeeId", payeeId,
                "amount", amount,
                "requestId", requestId,
                "remark", remark
            )
        );

        var action = post("/api/transfers/prepare")
            .contentType(MediaType.APPLICATION_JSON)
            .content(body);

        if (bearer != null) {
            action.header("Authorization", bearer);
        }

        String response = mvc.perform(action)
            .andExpect(status().isCreated())
            .andReturn()
            .getResponse()
            .getContentAsString();

        return mapper.readTree(response);
    }

    @Test
    void loginIsRequiredForAllAccountReadsAndWrites() throws Exception {

        mvc.perform(get("/api/demo/balance"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/demo/payees"))
            .andExpect(status().isUnauthorized());

        mvc.perform(
            post("/api/transfers/prepare")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"payeeId\":1,\"amount\":\"200.00\","
                    + "\"requestId\":\"unauth-12345\"}"
                )
        )
        .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/demo/health"))
            .andExpect(status().isOk());
    }

    @Test
    void demoLoginBadPasswordIsRejected() throws Exception {

        mvc.perform(
            post("/api/auth/demo-login")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"username\":\"demo\",\"password\":\"wrong\"}"
                )
        )
        .andExpect(status().isUnauthorized());
    }

    @Test
    void bearerFromBackendEnablesReadonlyApis() throws Exception {

        String auth = "Bearer " + token();

        mvc.perform(
            get("/api/demo/balance")
                .header("Authorization", auth)
        )
        .andExpect(status().isOk())
        .andExpect(
            jsonPath("$.accountNoMasked").value("****6688")
        );

        mvc.perform(
            get("/api/demo/payees")
                .header("Authorization", auth)
        )
        .andExpect(status().isOk())
        .andExpect(
            jsonPath("$[0].payeeName").value("李四")
        );
    }

    @Test
    void prepareDoesNotChangeEitherBalanceOrExistingTransactions()
        throws Exception {

        BigDecimal beforeA = jdbc.queryForObject(
            "SELECT balance FROM accounts WHERE id=1",
            BigDecimal.class
        );

        BigDecimal beforeB = jdbc.queryForObject(
            "SELECT balance FROM accounts WHERE id=2",
            BigDecimal.class
        );

        Integer beforeRows = jdbc.queryForObject(
            "SELECT count(*) FROM transactions",
            Integer.class
        );

        JsonNode result = order(
            "Bearer " + token(),
            "prepare-10101",
            "200.00",
            1,
            "AA晚餐"
        );

        assertThat(result.get("status").asText())
            .isEqualTo("PENDING_APPROVAL");

        assertThat(result.get("riskLevel").asText())
            .isEqualTo("YELLOW");

        assertThat(result.get("accountMasked").asText())
            .isEqualTo("****5291");

        assertThat(
            jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id=1",
                BigDecimal.class
            )
        ).isEqualByComparingTo(beforeA);

        assertThat(
            jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id=2",
                BigDecimal.class
            )
        ).isEqualByComparingTo(beforeB);

        assertThat(
            jdbc.queryForObject(
                "SELECT count(*) FROM transactions",
                Integer.class
            )
        ).isEqualTo(beforeRows);

        assertThat(
            jdbc.queryForObject(
                "SELECT count(*) FROM approval_records",
                Integer.class
            )
        ).isZero();
    }

    @Test
    void duplicateRequestReturnsSameOrderWithoutDoubleInsert()
        throws Exception {

        String auth = "Bearer " + token();

        JsonNode first = order(
            auth, "prepare-20202", "200.00", 1, "AA"
        );

        JsonNode second = order(
            auth, "prepare-20202", "200", 1, "AA"
        );

        assertThat(second.get("orderId").asLong())
            .isEqualTo(first.get("orderId").asLong());

        assertThat(
            jdbc.queryForObject(
                "SELECT count(*) FROM transfer_orders",
                Integer.class
            )
        ).isEqualTo(1);
    }

    @Test
    void duplicateRequestDifferentParametersIsConflict()
        throws Exception {

        String auth = "Bearer " + token();

        order(
            auth, "prepare-30303", "200.00", 1, "AA"
        );

        mvc.perform(
            post("/api/transfers/prepare")
                .header("Authorization", auth)
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"payeeId\":1,\"amount\":\"300.00\","
                    + "\"requestId\":\"prepare-30303\","
                    + "\"remark\":\"AA\"}"
                )
        )
        .andExpect(status().isConflict());

        assertThat(
            jdbc.queryForObject(
                "SELECT count(*) FROM transfer_orders",
                Integer.class
            )
        ).isEqualTo(1);
    }

    @Test
    void pendingOrdersAreCountedTowardsRisk() throws Exception {

        String auth = "Bearer " + token();

        assertThat(
            order(
                auth, "prepare-40001", "800.00", 1, ""
            ).get("riskLevel").asText()
        ).isEqualTo("YELLOW");

        assertThat(
            order(
                auth, "prepare-40002", "500.00", 1, ""
            ).get("riskLevel").asText()
        ).isEqualTo("RED");
    }

    @Test
    void rejectsInvalidAmountAndForeignPayee() throws Exception {

        String auth = "Bearer " + token();

        // Each invalid amount uses an independent, valid requestId.
        // This ensures that the test checks amount validation
        // rather than failing early on requestId validation.

        String[] invalidAmounts = {
            "0",
            "-1",
            "200.123",
            "1e2",
            "1000000.01"
        };

        int caseIndex = 0;

        for (String amount : invalidAmounts) {

            // Only letters, numbers and hyphens are used.
            // The original invalid amount is not part of requestId.
            String requestId =
                "amt-invalid-" + (++caseIndex) + "-xxxxx";

            String body = mapper.writeValueAsString(
                Map.of(
                    "payeeId", 1,
                    "amount", amount,
                    "requestId", requestId
                )
            );

            mvc.perform(
                post("/api/transfers/prepare")
                    .header("Authorization", auth)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body)
            )
            .andExpect(status().isUnprocessableEntity());
        }

        // Reject a payee that does not belong to the demo user.
        mvc.perform(
            post("/api/transfers/prepare")
                .header("Authorization", auth)
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"payeeId\":2,\"amount\":\"100.00\","
                    + "\"requestId\":\"foreign-12345\"}"
                )
        )
        .andExpect(status().isNotFound());

        // Invalid requests must not create transfer orders.
        assertThat(
            jdbc.queryForObject(
                "SELECT count(*) FROM transfer_orders",
                Integer.class
            )
        ).isZero();
    }

    @Test
    void logoutRevokesToken() throws Exception {

        String auth = "Bearer " + token();

        mvc.perform(
            post("/api/auth/logout")
                .header("Authorization", auth)
        )
        .andExpect(status().isOk());

        mvc.perform(
            get("/api/demo/balance")
                .header("Authorization", auth)
        )
        .andExpect(status().isUnauthorized());
    }
}
