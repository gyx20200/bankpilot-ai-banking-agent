package com.bankpilot.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

/** D12 negative security test. Does not require seed users or demo tokens. */
@SpringBootTest
@AutoConfigureMockMvc
class Day12ReadOnlyAuthTest {
    @Autowired MockMvc mvc;

    @Test
    void sixPrivateReadEndpointsRejectAnonymousRequests() throws Exception {
        String[] urls = {
            "/api/demo/balance",
            "/api/demo/transactions",
            "/api/demo/payees",
            "/api/demo/subscriptions",
            "/api/demo/analytics/monthly?month=2026-10",
            "/api/demo/analytics/anomalies?month=2026-10"
        };
        for (String url : urls) {
            int code = mvc.perform(get(url)).andReturn().getResponse().getStatus();
            assertTrue(code == 401 || code == 403,
                "Anonymous bank read must be 401/403; path=" + url + ", status=" + code);
        }
    }
}
