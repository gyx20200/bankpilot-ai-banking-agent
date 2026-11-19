package com.bankpilot.demo;

import com.fasterxml.jackson.databind.JsonNode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Iterator;
import java.util.Set;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/**
 * D3 conversation API. Java is the authoritative identity and data owner.
 * Public clients can append USER messages only, never ASSISTANT or SYSTEM.
 * This controller does NOT execute or resume any banking workflow.
 */
@RestController
@RequestMapping("/api/conversations")
public class ConversationController {
    private static final Set<String> CREATE_FIELDS = Set.of("title");
    private static final Set<String> MESSAGE_FIELDS = Set.of("content", "requestId");
    private static final Set<String> ASSISTANT_FIELDS =
            Set.of("content", "requestId", "userMessageRequestId", "userMessageContent");

    /** A separate server-to-server secret; never exposed to the browser. */
    @Value("${BANKPILOT_AGENT_INTERNAL_KEY:}")
    private String agentInternalKey;

    private final ConversationService service;

    public ConversationController(ConversationService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<ConversationService.ConversationView> create(
            @RequestBody(required = false) JsonNode body) {
        onlyFields(body, CREATE_FIELDS);
        var view = service.create(AuthenticatedUser.id(), optionalText(body, "title"));
        return ResponseEntity.status(HttpStatus.CREATED).body(view);
    }

    @GetMapping
    public ConversationService.ConversationList list(
            @RequestParam(defaultValue = "20") int limit,
            @RequestParam(required = false) String cursor) {
        return service.list(AuthenticatedUser.id(), limit, cursor);
    }

    @GetMapping("/{id}")
    public ConversationService.ConversationView get(@PathVariable String id) {
        return service.get(AuthenticatedUser.id(), id);
    }

    @GetMapping("/{id}/messages")
    public ConversationService.MessageList messages(
            @PathVariable String id,
            @RequestParam(defaultValue = "20") int limit,
            @RequestParam(required = false) Long beforeId) {
        return service.messages(AuthenticatedUser.id(), id, limit, beforeId);
    }

    @PostMapping("/{id}/messages")
    public ResponseEntity<ConversationService.MessageView> appendUserMessage(
            @PathVariable String id,
            @RequestBody(required = false) JsonNode body) {
        onlyFields(body, MESSAGE_FIELDS);
        // No request 'role' or 'userId' may reach the service.
        String content = requiredText(body, "content");
        String requestId = requiredText(body, "requestId");
        var result = service.appendUserMessage(
                AuthenticatedUser.id(), id, content, requestId);
        // An idempotent retry returns the original message with HTTP 200.
        return ResponseEntity.status(result.created() ? HttpStatus.CREATED : HttpStatus.OK)
                .body(result.message());
    }

    /**
     * Trusted FastAPI-to-Java history write.
     * Both an authenticated user's Bearer token AND the private service key
     * are required. Browser users cannot create ASSISTANT history rows.
     */
    @PostMapping("/{id}/assistant-messages")
    public ResponseEntity<ConversationService.MessageView> appendAssistantMessage(
            @PathVariable String id,
            @RequestHeader(value = "X-Bankpilot-Agent-Key", required = false) String serviceKey,
            @RequestBody(required = false) JsonNode body) {
        long userId = AuthenticatedUser.id();
        requireTrustedAgent(serviceKey);
        onlyFields(body, ASSISTANT_FIELDS);
        String content = requiredText(body, "content");
        String requestId = requiredText(body, "requestId");
        String sourceRequestId = requiredText(body, "userMessageRequestId");
        String sourceContent = requiredText(body, "userMessageContent");
        var result = service.appendAssistantMessage(
                userId, id, content, requestId, sourceRequestId, sourceContent);
        return ResponseEntity.status(result.created() ? HttpStatus.CREATED : HttpStatus.OK)
                .body(result.message());
    }

    private void requireTrustedAgent(String supplied) {
        if (agentInternalKey == null
                || agentInternalKey.getBytes(StandardCharsets.UTF_8).length < 32) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                    "Agent history writer is not configured");
        }
        byte[] actual = agentInternalKey.getBytes(StandardCharsets.UTF_8);
        byte[] candidate = supplied == null ? new byte[0]
                : supplied.getBytes(StandardCharsets.UTF_8);
        if (!MessageDigest.isEqual(actual, candidate)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN,
                    "Trusted Agent service credentials required");
        }
    }

    private static void onlyFields(JsonNode body, Set<String> allowed) {
        if (body == null || !body.isObject()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "JSON object required");
        }
        Iterator<String> names = body.fieldNames();
        while (names.hasNext()) {
            if (!allowed.contains(names.next())) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                        "Unexpected request field");
            }
        }
    }

    private static String optionalText(JsonNode body, String key) {
        JsonNode value = body.get(key);
        if (value == null || value.isNull()) return null;
        if (!value.isTextual()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    key + " must be a string");
        }
        return value.textValue();
    }

    private static String requiredText(JsonNode body, String key) {
        JsonNode value = body.get(key);
        if (value == null || !value.isTextual()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    key + " is required and must be a string");
        }
        return value.textValue();
    }
}
