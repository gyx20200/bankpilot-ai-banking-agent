package com.bankpilot.demo;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class CapabilityCatalogTest {
    @Test
    void staticWhitelistIsExtensibleButContainsNoExecutionTool() {
        var catalog = new AgentCapabilityController().capabilities();
        assertEquals(3, catalog.capabilities().size());
        assertTrue(catalog.capabilities().stream().anyMatch(c -> c.type().equals("monthly_analytics") && c.requiredParams().contains("month")));
        assertTrue(catalog.capabilities().stream().anyMatch(c -> c.type().equals("cancel_subscription") && c.requiresApproval()));
        assertFalse(catalog.capabilities().stream().anyMatch(c -> c.operation().contains("/authorize") || c.operation().contains("/execute")));
    }
}
