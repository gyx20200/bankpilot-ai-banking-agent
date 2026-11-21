package com.bankpilot.demo;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.Iterator;
import java.util.Set;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

/** Only for trusted FastAPI server calls. No bank order writes or OTPs here. */
@RestController
@RequestMapping("/api/workflow-recovery-claims")
public class WorkflowRecoveryController {
    private static final String AGENT_KEY = "X-Bankpilot-Agent-Key";
    private static final Set<String> CLAIM_FIELDS = Set.of(
            "threadId", "actionId", "checkpointId", "approved");
    private static final Set<String> FINALIZE_FIELDS = Set.of("status");
    private final WorkflowRecoveryService service;
    private final WorkflowSessionService registry;

    public WorkflowRecoveryController(WorkflowRecoveryService service,
                                      WorkflowSessionService registry) {
        this.service = service;
        this.registry = registry;
    }

    private long trusted(String internalKey) {
        long userId = AuthenticatedUser.id();
        registry.requireTrustedAgent(internalKey);
        return userId;
    }

    private static void onlyFields(JsonNode body, Set<String> allowed) {
        if (body == null || !body.isObject()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "JSON object required");
        }
        Iterator<String> names = body.fieldNames();
        while (names.hasNext()) {
            if (!allowed.contains(names.next())) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Unexpected JSON field");
            }
        }
    }

    private static String requiredText(JsonNode obj, String key) {
        JsonNode n = obj.get(key);
        if (n == null || !n.isTextual() || n.textValue().isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, key + " must be a string");
        }
        return n.textValue();
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public WorkflowRecoveryService.ClaimView claim(
            @RequestHeader(value=AGENT_KEY, required=false) String key,
            @RequestBody(required=false) JsonNode body) {
        long userId = trusted(key);
        onlyFields(body, CLAIM_FIELDS);
        JsonNode approved = body.get("approved");
        if (approved == null || !approved.isBoolean()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "approved must be boolean");
        }
        return service.claim(userId, requiredText(body, "threadId"),
                requiredText(body, "actionId"), requiredText(body, "checkpointId"),
                approved.booleanValue());
    }

    @GetMapping("/{threadId}")
    public WorkflowRecoveryService.ClaimView get(
            @RequestHeader(value=AGENT_KEY, required=false) String key,
            @PathVariable String threadId) {
        return service.get(trusted(key), threadId);
    }

    @PostMapping("/{threadId}/finalize")
    public WorkflowRecoveryService.ClaimView finalizeClaim(
            @RequestHeader(value=AGENT_KEY, required=false) String key,
            @PathVariable String threadId,
            @RequestBody(required=false) JsonNode body) {
        long userId = trusted(key);
        onlyFields(body, FINALIZE_FIELDS);
        return service.finalizeClaim(userId, threadId, requiredText(body, "status"));
    }
}
