package com.bankpilot.demo;

import java.math.BigDecimal;
import java.sql.Statement;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/**
 * Day6 demo ONLY. The Agent may request a cancellation draft, never approve it.
 * Java enforces owner, idempotency and a separate explicit-approval state.
 * SUCCESS is for a simulated BANK debit mandate, not cancellation of a merchant contract.
 */
@Service
public class SubscriptionCancellationService {
    private static final ZoneId ZONE = ZoneId.of("Asia/Shanghai");
    private final JdbcTemplate jdbc;

    public SubscriptionCancellationService(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public record OrderView(long orderId, long subscriptionId, String merchantName,
                            BigDecimal amount, String billingCycle, String status,
                            String riskLevel, String workflowId, String expiresAt) { }
    private record Order(long id, long subscriptionId, String status,
                         LocalDateTime expiresAt, OrderView view) { }
    private record Subscription(long id, String name, BigDecimal amount,
                                String cycle, String status) { }

    private static Timestamp ts(LocalDateTime date) { return Timestamp.valueOf(date); }
    private static LocalDateTime now() { return LocalDateTime.now(ZONE); }
    private static void bad(String message) {
        throw new ResponseStatusException(HttpStatus.BAD_REQUEST, message);
    }
    private static void conflict(String message) {
        throw new ResponseStatusException(HttpStatus.CONFLICT, message);
    }

    private void audit(long userId, long orderId, String action, String result) {
        jdbc.update("""
            INSERT INTO subscription_cancel_events(order_id,user_id,action,result,created_at)
            VALUES (?,?,?,?,?)
            """, orderId, userId, action, result, ts(now()));
    }

    private Order load(long userId, long orderId, boolean lock) {
        String sql = """
            SELECT id,subscription_id,merchant_name,amount,billing_cycle,
                   status,workflow_id,expires_at
            FROM subscription_cancel_orders WHERE id=? AND user_id=?
            """ + (lock ? " FOR UPDATE" : "");
        List<Order> result = jdbc.query(sql, (rs,i) -> {
            LocalDateTime expiry = rs.getTimestamp("expires_at").toLocalDateTime();
            String workflowId = rs.getString("workflow_id");
            OrderView view = new OrderView(rs.getLong("id"), rs.getLong("subscription_id"),
                rs.getString("merchant_name"),rs.getBigDecimal("amount"),
                rs.getString("billing_cycle"),rs.getString("status"),"YELLOW",
                workflowId, expiry.toString());
            return new Order(view.orderId(),view.subscriptionId(),view.status(),expiry,view);
        }, orderId, userId);
        if (result.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Cancellation order not found");
        return result.get(0);
    }

    private void lockUser(long userId) {
        List<Long> users = jdbc.query("SELECT id FROM users WHERE id=? FOR UPDATE",
            (rs,i) -> rs.getLong(1), userId);
        if (users.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "User not found");
    }

    @Transactional
    public OrderView prepare(long userId, SubscriptionCancellationController.PrepareRequest request) {
        if (request == null || request.subscriptionId() == null || request.subscriptionId() <= 0) {
            bad("subscriptionId is required");
        }
        if (request.requestId() == null || !request.requestId().matches("[A-Za-z0-9_-]{8,64}")) {
            bad("requestId must be 8-64 characters of A-Z, a-z, digits, _ or -");
        }
        String workflowId = request.workflowId();
        if (workflowId != null && !workflowId.matches("[A-Za-z0-9_-]{8,64}")) {
            bad("workflowId must be 8-64 safe characters");
        }
        lockUser(userId); // Serializes same-user prepares; protects request-id deduplication.

        var existing = jdbc.query("""
            SELECT id,subscription_id,workflow_id FROM subscription_cancel_orders
            WHERE user_id=? AND request_id=?
            """, (rs,i) -> new Existing(rs.getLong("id"), rs.getLong("subscription_id"),
                rs.getString("workflow_id")),userId,request.requestId());
        if (!existing.isEmpty()) {
            Existing found = existing.get(0);
            if (found.subscriptionId() != request.subscriptionId() ||
                !java.util.Objects.equals(found.workflowId(),workflowId)) {
                conflict("requestId already used for a different cancellation");
            }
            return load(userId,found.id(),false).view();
        }

        var subscriptions = jdbc.query("""
            SELECT id,merchant_name,amount,billing_cycle,status FROM subscriptions
            WHERE id=? AND user_id=?
            """, (rs,i) -> new Subscription(rs.getLong("id"),rs.getString("merchant_name"),
                rs.getBigDecimal("amount"),rs.getString("billing_cycle"),rs.getString("status")),
            request.subscriptionId(), userId);
        if (subscriptions.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Subscription not found");
        Subscription subscription = subscriptions.get(0);
        if (!"ACTIVE".equals(subscription.status())) conflict("Subscription is already cancelled");

        Integer pending = jdbc.queryForObject("""
            SELECT COUNT(*) FROM subscription_cancel_orders
            WHERE user_id=? AND subscription_id=? AND status IN ('PENDING_APPROVAL','AUTHORIZED') AND expires_at>?
            """, Integer.class, userId, request.subscriptionId(), ts(now()));
        if (pending != null && pending > 0) conflict("An active cancellation request already exists");

        LocalDateTime now = now();
        LocalDateTime expires = now.plusMinutes(15);
        GeneratedKeyHolder holder = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            var statement = connection.prepareStatement("""
                INSERT INTO subscription_cancel_orders
                (user_id,subscription_id,request_id,workflow_id,merchant_name,amount,billing_cycle,
                 status,expires_at,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,'PENDING_APPROVAL',?,?,?)
                """, Statement.RETURN_GENERATED_KEYS);
            statement.setLong(1,userId);
            statement.setLong(2,subscription.id());
            statement.setString(3,request.requestId());
            statement.setString(4,workflowId);
            statement.setString(5,subscription.name());
            statement.setBigDecimal(6,subscription.amount());
            statement.setString(7,subscription.cycle());
            statement.setTimestamp(8,ts(expires));
            statement.setTimestamp(9,ts(now));
            statement.setTimestamp(10,ts(now));
            return statement;
        },holder);
        if (holder.getKey() == null) throw new IllegalStateException("Generated order ID missing");
        long orderId = holder.getKey().longValue();
        audit(userId,orderId,"PREPARE","PENDING_APPROVAL");
        return load(userId,orderId,false).view();
    }
    private record Existing(long id,long subscriptionId,String workflowId) { }

    @Transactional(readOnly = true)
    public OrderView status(long userId, long orderId) {
        return load(userId,orderId,false).view();
    }

    @Transactional
    public OrderView authorize(long userId,long orderId,boolean confirmed) {
        Order order = load(userId,orderId,true);
        if ("SUCCESS".equals(order.status())) conflict("Already executed; cannot change authorization");
        if ("CANCELLED".equals(order.status())) {
            if (!confirmed) return order.view(); // Repeated decline is idempotent.
            conflict("Order was already declined");
        }
        if (!confirmed) {
            jdbc.update("""
                UPDATE subscription_cancel_orders SET status='CANCELLED',updated_at=? WHERE id=?
                """,ts(now()),orderId);
            audit(userId,orderId,"USER_DECISION","DECLINED");
            return load(userId,orderId,false).view();
        }
        if (!order.expiresAt().isAfter(now())) conflict("Cancellation request expired, please prepare again");
        if ("AUTHORIZED".equals(order.status())) return order.view(); // No duplicate approval.
        jdbc.update("""
            UPDATE subscription_cancel_orders SET status='AUTHORIZED', authorized_at=?, updated_at=? WHERE id=?
            """,ts(now()),ts(now()),orderId);
        audit(userId,orderId,"USER_DECISION","CONFIRMED");
        return load(userId,orderId,false).view();
    }

    @Transactional
    public OrderView execute(long userId,long orderId) {
        Order order = load(userId,orderId,true);
        if ("SUCCESS".equals(order.status())) return order.view(); // Repeat safe, no second mutation.
        if (!"AUTHORIZED".equals(order.status())) conflict("Explicit user authorization is required");
        if (!order.expiresAt().isAfter(now())) conflict("Cancellation request expired; please prepare again");
        // Update is conditional to prevent accidental re-cancellation if another flow already cancelled.
        int changed = jdbc.update("""
            UPDATE subscriptions SET status='CANCELLED',cancelled_at=?,next_pay_date=NULL
            WHERE id=? AND user_id=? AND status='ACTIVE'
            """,ts(now()),order.subscriptionId(),userId);
        if (changed != 1) conflict("Subscription is no longer active");
        jdbc.update("""
            UPDATE subscription_cancel_orders SET status='SUCCESS',executed_at=?,updated_at=? WHERE id=?
            """,ts(now()),ts(now()),orderId);
        audit(userId,orderId,"EXECUTE","SUCCESS");
        return load(userId,orderId,false).view();
    }
}
