package com.bankpilot.demo;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.Iterator;
import java.util.Set;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/** D5 internal workflow registry API. This controller never executes a bank order. */
@RestController
@RequestMapping("/api/workflow-sessions")
public class WorkflowSessionController {
    private static final String AGENT_KEY = "X-Bankpilot-Agent-Key";
    private static final Set<String> REGISTER_FIELDS = Set.of(
            "threadId", "conversationId", "sourceRequestId", "userMessageContent");
    private static final Set<String> STATUS_FIELDS = Set.of("status");

    private final WorkflowSessionService service;

    public WorkflowSessionController(WorkflowSessionService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public WorkflowSessionService.SessionView register(
            @RequestHeader(value = AGENT_KEY, required = false) String serviceKey,
            @RequestBody(required = false) JsonNode body) {
        long userId = trustedUser(serviceKey);
        onlyFields(body, REGISTER_FIELDS);
        return service.register(userId,
                requiredText(body, "threadId"),
                requiredText(body, "conversationId"),
                requiredText(body, "sourceRequestId"),
                requiredText(body, "userMessageContent"));
    }

    @GetMapping("/{threadId}")
    public WorkflowSessionService.SessionView get(
            @RequestHeader(value = AGENT_KEY, required = false) String serviceKey,
            @PathVariable String threadId) {
        return service.get(trustedUser(serviceKey), threadId);
    }

    @GetMapping
    public WorkflowSessionService.SessionList list(
            @RequestHeader(value = AGENT_KEY, required = false) String serviceKey,
            @RequestParam String conversationId,
            @RequestParam(defaultValue = "20") int limit) {
        return service.list(trustedUser(serviceKey), conversationId, limit);
    }

    @PatchMapping("/{threadId}/status")
    public WorkflowSessionService.SessionView updateStatus(
            @RequestHeader(value = AGENT_KEY, required = false) String serviceKey,
            @PathVariable String threadId,
            @RequestBody(required = false) JsonNode body) {
        long userId = trustedUser(serviceKey);
        onlyFields(body, STATUS_FIELDS);
        return service.updateStatus(userId, threadId, requiredText(body, "status"));
    }

    private long trustedUser(String serviceKey) {
        long userId = AuthenticatedUser.id();
        service.requireTrustedAgent(serviceKey);
        return userId;
    }

    private static void onlyFields(JsonNode body, Set<String> allowed) {
        if (body == null || !body.isObject()) {
            throw bad("JSON object required");
        }
        Iterator<String> names = body.fieldNames();
        while (names.hasNext()) {
            if (!allowed.contains(names.next())) {
                throw bad("Unexpected request field");
            }
        }
    }

    private static String requiredText(JsonNode body, String key) {
        JsonNode value = body.get(key);
        if (value == null || !value.isTextual() || value.textValue().isBlank()) {
            throw bad(key + " is required and must be a nonblank string");
        }
        return value.textValue();
    }

    private static ResponseStatusException bad(String reason) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, reason);
    }
}
