package com.bankpilot.demo;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

/** Day 6: Registry is bank-authoritative for a validated plan and cancellation status,
 * NOT a replacement for LangGraph checkpointing or the user's explicit approval. */
@RestController
@RequestMapping("/api/agent/workflow-runs")
public class AgentWorkflowRegistryController {
    private final AgentWorkflowRegistryService registry;

    public AgentWorkflowRegistryController(AgentWorkflowRegistryService registry) {
        this.registry = registry;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public AgentWorkflowRegistryService.WorkflowSnapshot register(
            @RequestBody AgentWorkflowRegistryService.RegisterRequest request) {
        return registry.register(AuthenticatedUser.id(), request);
    }

    @GetMapping("/{workflowId}")
    public AgentWorkflowRegistryService.WorkflowSnapshot snapshot(@PathVariable String workflowId) {
        return registry.snapshot(AuthenticatedUser.id(), workflowId);
    }
}
