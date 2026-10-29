package com.bankpilot.demo;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.Statement;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.YearMonth;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Set;

import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/**
 * Durable, tenant-scoped registration of the A/B/C task plan.
 * No calls to execute, approve or cancel occur in this registry.
 * Read task *execution* belongs to the Python graph; MySQL bank orders remain truth.
 */
@Service
public class AgentWorkflowRegistryService {
    private static final List<String> ORDER = List.of(
        "monthly_analytics", "list_subscriptions", "cancel_subscription");
    private final JdbcTemplate jdbc;

    public AgentWorkflowRegistryService(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public record TaskInput(String type, String month, String merchantName) { }
    public record RegisterRequest(String workflowId, List<TaskInput> tasks) { }
    public record TaskView(String type, String month, String merchantName,
                           List<String> dependsOn, String executionOwner) { }
    public record CancellationView(long orderId, long subscriptionId,
                                   String merchantName, String status, String riskLevel, LocalDateTime expiresAt) { }
    public record WorkflowSnapshot(String workflowId, List<TaskView> tasks,
        String businessPhase, List<CancellationView> cancellationOrders,
        String checkpointNote) { }
    private record StoredRun(long id, String planHash) { }
    private record CanonicalTask(String type, String month, String merchantName) { }

    private static ResponseStatusException bad(String msg) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, msg);
    }
    private static ResponseStatusException conflict(String msg) {
        return new ResponseStatusException(HttpStatus.CONFLICT, msg);
    }
    private static boolean safeId(String id) {
        return id != null && id.matches("[A-Za-z0-9_-]{8,64}");
    }
    private static String validMonth(String value) {
        if (value == null || !value.matches("[0-9]{4}-(0[1-9]|1[0-2])"))
            throw bad("month must be YYYY-MM");
        try { YearMonth.parse(value); }
        catch (DateTimeParseException exc) { throw bad("invalid month"); }
        return value;
    }
    private static List<CanonicalTask> normalize(List<TaskInput> tasks) {
        if (tasks == null || tasks.isEmpty() || tasks.size() > 3)
            throw bad("A plan must contain 1 to 3 tasks");
        Set<String> seen = new HashSet<>();
        List<CanonicalTask> result = new ArrayList<>();
        for (TaskInput task : tasks) {
            if (task == null || !ORDER.contains(task.type()))
                throw bad("Unknown task type");
            if (!seen.add(task.type())) throw bad("Duplicate task type");
            switch (task.type()) {
                case "monthly_analytics" -> {
                    if (task.merchantName() != null && !task.merchantName().isBlank())
                        throw bad("monthly task cannot set merchantName");
                    result.add(new CanonicalTask(task.type(), validMonth(task.month()), null));
                }
                case "list_subscriptions" -> {
                    if (task.month() != null || task.merchantName() != null)
                        throw bad("subscription list task takes no params");
                    result.add(new CanonicalTask(task.type(), null, null));
                }
                case "cancel_subscription" -> {
                    if (task.month() != null) throw bad("cancel task cannot set month");
                    String merchant = task.merchantName();
                    if (merchant == null || merchant.isBlank() || merchant.length() > 100)
                        throw bad("cancel_subscription requires a merchantName");
                    // Merchant name is treated as DATA, not commands. Trim only.
                    result.add(new CanonicalTask(task.type(), null, merchant.trim()));
                }
                default -> throw bad("Unknown task type");
            }
        }
        result.sort(Comparator.comparingInt(t -> ORDER.indexOf(t.type())));
        return List.copyOf(result);
    }
    private static String hash(List<CanonicalTask> tasks) {
        StringBuilder content = new StringBuilder();
        for (CanonicalTask t : tasks) {
            for (String field : List.of(t.type(), t.month() == null ? "" : t.month(),
                                          t.merchantName() == null ? "" : t.merchantName())) {
                content.append(field.length()).append(':').append(field);
            }
        }
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(content.toString().getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException exc) { throw new IllegalStateException(exc); }
    }
    private void lockUser(long userId) {
        var users = jdbc.query("SELECT id FROM users WHERE id=? FOR UPDATE", (rs,i) -> rs.getLong(1),userId);
        if (users.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"User not found");
    }

    @Transactional
    public WorkflowSnapshot register(long userId, RegisterRequest request) {
        if (request == null || !safeId(request.workflowId())) throw bad("Invalid workflowId");
        List<CanonicalTask> tasks = normalize(request.tasks());
        String fingerprint = hash(tasks);
        lockUser(userId); // serializes same-user create/idempotent retries
        List<StoredRun> existing = jdbc.query("""
            SELECT id,plan_hash FROM agent_workflow_runs WHERE user_id=? AND workflow_id=?
            """, (rs,i)->new StoredRun(rs.getLong("id"),rs.getString("plan_hash")),userId,request.workflowId());
        if (!existing.isEmpty()) {
            if (!existing.get(0).planHash().equals(fingerprint))
                throw conflict("workflowId already registered with a different task plan");
            return snapshot(userId,request.workflowId());
        }
        GeneratedKeyHolder holder = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            var statement = connection.prepareStatement("""
                INSERT INTO agent_workflow_runs(user_id,workflow_id,plan_hash,created_at)
                VALUES(?,?,?,?)
                """,Statement.RETURN_GENERATED_KEYS);
            statement.setLong(1,userId);
            statement.setString(2,request.workflowId());
            statement.setString(3,fingerprint);
            statement.setTimestamp(4,Timestamp.valueOf(LocalDateTime.now()));
            return statement;
        },holder);
        if (holder.getKey()==null) throw new IllegalStateException("Missing workflow ID");
        long runId = holder.getKey().longValue();
        for (CanonicalTask task : tasks) {
            jdbc.update("""
                INSERT INTO agent_workflow_tasks(run_id,task_type,month_value,merchant_name)
                VALUES(?,?,?,?)
                """,runId,task.type(),task.month(),task.merchantName());
        }
        return snapshot(userId,request.workflowId());
    }

    @Transactional(readOnly=true)
    public WorkflowSnapshot snapshot(long userId,String workflowId) {
        if (!safeId(workflowId)) throw bad("Invalid workflowId");
        var rows = jdbc.query("""
            SELECT id FROM agent_workflow_runs WHERE user_id=? AND workflow_id=?
            """,(rs,i)->rs.getLong(1),userId,workflowId);
        if (rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Workflow plan not found");
        long runId = rows.get(0);
        var rowsTasks = jdbc.query("""
            SELECT task_type,month_value,merchant_name FROM agent_workflow_tasks
            WHERE run_id=? ORDER BY CASE task_type
              WHEN 'monthly_analytics' THEN 1 WHEN 'list_subscriptions' THEN 2 ELSE 3 END
            """,(rs,i)->new CanonicalTask(rs.getString("task_type"),rs.getString("month_value"),
                rs.getString("merchant_name")),runId);
        boolean explicitSubscriptions = rowsTasks.stream().anyMatch(t -> t.type().equals("list_subscriptions"));
        boolean includesCancel = rowsTasks.stream().anyMatch(t -> t.type().equals("cancel_subscription"));
        List<TaskView> views = rowsTasks.stream().map(t -> new TaskView(t.type(),t.month(),t.merchantName(),
            t.type().equals("cancel_subscription")
                ? List.of(explicitSubscriptions ? "list_subscriptions" : "internal_subscription_lookup", "human_approval")
                : List.of(), "python_langgraph")).toList();
        List<CancellationView> orders = jdbc.query("""
            SELECT id,subscription_id,merchant_name,status,expires_at FROM subscription_cancel_orders
            WHERE user_id=? AND workflow_id=? ORDER BY id ASC
            """,(rs,i)->new CancellationView(rs.getLong("id"),rs.getLong("subscription_id"),
                rs.getString("merchant_name"),rs.getString("status"),"YELLOW",
                rs.getTimestamp("expires_at").toLocalDateTime()),userId,workflowId);
        String phase;
        String requestedMerchant = rowsTasks.stream()
            .filter(t -> t.type().equals("cancel_subscription"))
            .map(CanonicalTask::merchantName).findFirst().orElse(null);
        if (!includesCancel) phase=orders.isEmpty() ? "READ_ONLY_PLAN" : "UNPLANNED_CANCEL_ORDER_REVIEW";
        else if (orders.isEmpty()) phase="CANCELLATION_NOT_PREPARED";
        else if (orders.size()>1) phase="MULTIPLE_ORDERS_REQUIRES_REVIEW";
        else if (!orders.get(0).merchantName().equals(requestedMerchant))
            phase="ORDER_TARGET_MISMATCH_REQUIRES_REVIEW";
        else if (("PENDING_APPROVAL".equals(orders.get(0).status()) || "AUTHORIZED".equals(orders.get(0).status()))
              && !orders.get(0).expiresAt().isAfter(LocalDateTime.now(ZoneId.of("Asia/Shanghai"))))
            phase="EXPIRED_REPREPARE_REQUIRED";
        else phase=switch(orders.get(0).status()) {
            case "PENDING_APPROVAL" -> "WAITING_USER_APPROVAL";
            case "AUTHORIZED" -> "AUTHORIZED_NOT_EXECUTED";
            case "SUCCESS" -> "BANK_CANCEL_SUCCESS";
            case "CANCELLED" -> "USER_DECLINED";
            default -> "UNKNOWN_RECHECK_BANK_ORDER";
        };
        return new WorkflowSnapshot(workflowId,views,phase,orders,
            "Java persists task plan and business order state only; LangGraph checkpoint and read results must be persisted in Python separately.");
    }
}
