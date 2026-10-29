package com.bankpilot.demo;

import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Optional Day6 dynamic workflow discovery endpoint.
 * A static whitelist, NOT a way for the LLM to enable or authorize tools.
 * Requires an authenticated request under existing SecurityConfig.anyRequest().authenticated().
 */
@RestController
@RequestMapping("/api/agent")
public class AgentCapabilityController {
    public record Capability(String type, String operation, String riskLevel,
                             boolean requiresApproval, List<String> requiredParams,
                             List<String> internalDependencies) { }
    public record Catalog(int version, List<Capability> capabilities, Map<String, String> notes) { }

    @GetMapping("/capabilities")
    public Catalog capabilities() {
        return new Catalog(1, List.of(
            new Capability("monthly_analytics", "GET /api/demo/analytics/monthly", "GREEN", false,
                List.of("month"), List.of()),
            new Capability("list_subscriptions", "GET /api/demo/subscriptions", "GREEN", false,
                List.of(), List.of()),
            new Capability("cancel_subscription", "POST /api/subscription-cancellations/prepare",
                "YELLOW", true, List.of("merchant_name"),
                List.of("list_subscriptions", "human_approval"))
        ), Map.of(
            "approval", "Authorize/execute are NOT model tools; explicit user action and backend validation required",
            "months", "YYYY-MM (data comes from MySQL; no rows does not imply missing API)",
            "source", "static-java-whitelist"
        ));
    }
}
