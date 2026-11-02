package com.bankpilot.demo;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

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
import org.springframework.test.web.servlet.MockMvc;

/** Existing 5-tool contract remains compatible with Day 5 DeepSeek Agent. */
@SpringBootTest
@AutoConfigureMockMvc
class AgentToolContractTest {
    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
    @Autowired ObjectMapper mapper;

    @BeforeEach
    void resetAudit() {
        jdbc.update("DELETE FROM agent_tool_events");
    }

    private String token() throws Exception {
        String request = mapper.writeValueAsString(Map.of("username", "demo", "password", "JUnitDemoPassword2026!"));
        String raw = mvc.perform(post("/api/auth/demo-login").contentType(MediaType.APPLICATION_JSON).content(request))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        return "Bearer " + mapper.readTree(raw).get("token").asText();
    }

    @Test
    void fiveKnownEndpointsStillUseOriginalJsonStructures() throws Exception {
        String auth = token();
        mvc.perform(get("/api/demo/balance").header("Authorization", auth))
            .andExpect(status().isOk()).andExpect(jsonPath("$.balance").exists())
            .andExpect(jsonPath("$.accountNoMasked").value("****6688"));
        mvc.perform(get("/api/demo/transactions").header("Authorization", auth))
            .andExpect(status().isOk()).andExpect(jsonPath("$[0].merchantName").exists());
        mvc.perform(get("/api/demo/payees").header("Authorization", auth))
            .andExpect(status().isOk()).andExpect(jsonPath("$[0].payeeName").value("李四"));
        mvc.perform(get("/api/demo/subscriptions").header("Authorization", auth))
            .andExpect(status().isOk()).andExpect(jsonPath("$[0].billingCycle").value("MONTHLY"));
        assertThat(jdbc.queryForObject("SELECT count(*) FROM agent_tool_events", Integer.class)).isEqualTo(4);
    }

    @Test
    void auditUsesTraceIdButDoesNotStorePromptsOrTokens() throws Exception {
        String auth = token();
        mvc.perform(get("/api/demo/balance").header("Authorization", auth)
            .header("X-Agent-Request-Id", "agent-day5-123456"))
            .andExpect(status().isOk())
            .andExpect(result -> assertThat(result.getResponse().getHeader("X-Agent-Request-Id"))
                .isEqualTo("agent-day5-123456"));
        var row = jdbc.queryForMap("SELECT * FROM agent_tool_events ORDER BY id DESC LIMIT 1");
        assertThat(row.get("request_id")).isEqualTo("agent-day5-123456");
        assertThat(row.get("tool_name")).isEqualTo("get_balance");
        assertThat(((Number) row.get("http_status")).intValue()).isEqualTo(200);
        assertThat(row).doesNotContainKeys("prompt", "token", "otp", "account_no");
    }

    @Test
    void unauthenticatedQueriesRemainForbiddenAndNotRecordedAsUserActivity() throws Exception {
        mvc.perform(get("/api/demo/balance")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/demo/analytics/monthly").param("month", "2026-10"))
            .andExpect(status().isUnauthorized());
        assertThat(jdbc.queryForObject("SELECT count(*) FROM agent_tool_events", Integer.class)).isZero();
    }

    @Test
    void deterministicMonthlyAnalyticsIsAuthenticatedAndAudited() throws Exception {
        String auth = token();
        mvc.perform(get("/api/demo/analytics/monthly").param("month", "2026-10")
                .header("Authorization", auth))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.totalIncome").value(8000.00))
            .andExpect(jsonPath("$.totalExpense").value(60.00))
            .andExpect(jsonPath("$.source").value("mysql"));
        assertThat(jdbc.queryForObject("SELECT tool_name FROM agent_tool_events LIMIT 1", String.class))
            .isEqualTo("get_monthly_analytics");
    }

    @Test
    void prepareReturnsPendingAndNeverChangesBalance() throws Exception {
        String auth = token();
        BigDecimal before = jdbc.queryForObject("SELECT balance FROM accounts WHERE id=1", BigDecimal.class);
        String payload = mapper.writeValueAsString(Map.of("payeeId",1,"amount","100.00",
            "requestId", "day5-contract-001-"+System.nanoTime(),"remark","Agent-test"));
        String response = mvc.perform(post("/api/transfers/prepare").header("Authorization", auth)
            .header("X-Agent-Request-Id", "day5-contract-trace")
            .contentType(MediaType.APPLICATION_JSON).content(payload))
            .andExpect(status().isCreated()).andReturn().getResponse().getContentAsString();
        JsonNode body = mapper.readTree(response);
        assertThat(body.get("status").asText()).isEqualTo("PENDING_APPROVAL");
        assertThat(body.get("riskLevel").asText()).isIn("YELLOW", "RED");
        assertThat(jdbc.queryForObject("SELECT balance FROM accounts WHERE id=1", BigDecimal.class))
            .isEqualByComparingTo(before);
        assertThat(jdbc.queryForObject("SELECT tool_name FROM agent_tool_events LIMIT 1", String.class))
            .isEqualTo("prepare_transfer");
    }
}
