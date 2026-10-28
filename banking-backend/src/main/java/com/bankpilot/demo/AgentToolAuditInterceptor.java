package com.bankpilot.demo;

import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.Map;
import java.util.UUID;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.servlet.HandlerInterceptor;

/**
 * Day 5 tool invocation audit. Only non-sensitive metadata is persisted.
 * Existing Day 4 audit_events remains authoritative for money movements.
 * A tool audit insert failure does not forge a successful banking result.
 */
public class AgentToolAuditInterceptor implements HandlerInterceptor {
    private static final Logger LOG = LoggerFactory.getLogger(AgentToolAuditInterceptor.class);
    private static final ZoneId BUSINESS_ZONE = ZoneId.of("Asia/Shanghai");
    private static final Map<String, String> TOOL_PATHS = Map.of(
        "/api/demo/balance", "get_balance",
        "/api/demo/transactions", "get_transactions",
        "/api/demo/payees", "get_payees",
        "/api/demo/subscriptions", "get_subscriptions",
        "/api/transfers/prepare", "prepare_transfer",
        "/api/demo/analytics/monthly", "get_monthly_analytics"
    );
    private static final String REQUEST_ID = AgentToolAuditInterceptor.class.getName() + ".requestId";
    private final JdbcTemplate jdbc;

    public AgentToolAuditInterceptor(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
        String incoming = request.getHeader("X-Agent-Request-Id");
        String id = incoming != null && incoming.matches("[A-Za-z0-9_-]{8,64}")
            ? incoming : UUID.randomUUID().toString();
        request.setAttribute(REQUEST_ID, id);
        response.setHeader("X-Agent-Request-Id", id);
        return true;
    }

    @Override
    public void afterCompletion(HttpServletRequest request, HttpServletResponse response,
                                Object handler, Exception error) {
        String name = TOOL_PATHS.get(request.getRequestURI());
        if (name == null) return;
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth == null || !(auth.getPrincipal() instanceof BankPrincipal principal)) return;
        Object requestId = request.getAttribute(REQUEST_ID);
        if (!(requestId instanceof String id)) return;
        try {
            jdbc.update("""
                INSERT INTO agent_tool_events
                  (user_id, request_id, tool_name, http_method, http_status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                principal.userId(), id, name, request.getMethod(), response.getStatus(),
                Timestamp.valueOf(LocalDateTime.now(BUSINESS_ZONE)));
        } catch (RuntimeException exc) {
            // Existing Day4 audit_events still persists transactional transfer actions.
            // Read-call tracing here is best-effort, never a replacement for bank auditing.
            LOG.warn("Day5 tool metadata audit unavailable: tool={} http_status={}", name, response.getStatus());
        }
    }
}
