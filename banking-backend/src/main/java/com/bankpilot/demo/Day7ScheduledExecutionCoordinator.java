package com.bankpilot.demo;

import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.*;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** One DB transaction per schedule, with row lock, auth revalidation and bank proof. */
@Service
public class Day7ScheduledExecutionCoordinator {
    private final JdbcTemplate jdbc;
    private final Day7ScheduledFundsPort rail;
    public Day7ScheduledExecutionCoordinator(JdbcTemplate jdbc,Day7ScheduledFundsPort rail){this.jdbc=jdbc;this.rail=rail;}

    @Transactional
    public void execute(long id){
        var rows=jdbc.queryForList("SELECT * FROM scheduled_transfers WHERE id=? FOR UPDATE",id);
        if(rows.isEmpty()) return;
        var s=rows.get(0);
        if(!"SCHEDULED".equals(s.get("status"))) return;
        var utc=Day7ScheduledService.dbDateTime(s.get("scheduled_at_utc"));
        if(utc.isAfter(LocalDateTime.now(ZoneOffset.UTC))) return;
        if(utc.plusSeconds(60).isBefore(LocalDateTime.now(ZoneOffset.UTC))) {
            jdbc.update("UPDATE scheduled_transfers SET status='MISSED',last_error_code='EXECUTION_WINDOW_MISSED',updated_at=NOW(6) WHERE id=?",id);
            return;
        }
        long owner=((Number)s.get("owner_user_id")).longValue();
        long sender=((Number)s.get("sender_account_id")).longValue();
        long receiver=((Number)s.get("receiver_account_id")).longValue();
        BigDecimal amount=(BigDecimal)s.get("amount");
        String remark=(String)s.get("remark");
        var when=utc.toInstant(ZoneOffset.UTC);
        var hash=Day7ScheduledService.scope(owner,sender,receiver,amount,when,remark);
        var auth=jdbc.queryForList("""
          SELECT scope_hash,covered_risk,status,valid_until,auth_method FROM scheduled_transfer_authorizations
          WHERE schedule_id=? AND user_id=? FOR UPDATE
          """,id,owner);
        if(auth.size()!=1 || !hash.equals(s.get("scope_hash")) || !hash.equals(auth.get(0).get("scope_hash"))
          || !"ACTIVE".equals(auth.get(0).get("status"))
          || (auth.get(0).get("valid_until")!=null && Day7ScheduledService.dbDateTime(auth.get(0).get("valid_until")).isBefore(LocalDateTime.now(ZoneOffset.UTC)))){
            fail(id,"INVALID_SCHEDULE_PREAUTH");return;
        }
        Integer eligible=jdbc.queryForObject("""
            SELECT COUNT(*) FROM users u JOIN accounts a ON a.user_id=u.id
            WHERE u.id=? AND u.status='ACTIVE' AND a.id=? AND a.status='ACTIVE'
            """,Integer.class,owner,sender);
        Integer receiving=jdbc.queryForObject("SELECT COUNT(*) FROM accounts WHERE id=? AND status='ACTIVE'",
            Integer.class,receiver);
        if(eligible==null || eligible!=1 || receiving==null || receiving!=1){fail(id,"ACCOUNT_NOT_ACTIVE");return;}
        // Serialize same-owner prepares with normal Day6 transfer risk calculation.
        var owners=jdbc.query("SELECT id FROM users WHERE id=? AND status='ACTIVE' FOR UPDATE",
            (rs,i)->rs.getLong(1),owner);
        if(owners.size()!=1){fail(id,"OWNER_NOT_ACTIVE");return;}
        var senderBalance=jdbc.queryForList("SELECT balance FROM accounts WHERE id=? AND status='ACTIVE'",sender);
        if(senderBalance.size()!=1 || ((BigDecimal)senderBalance.get(0).get("balance")).compareTo(amount)<0){
            jdbc.update("UPDATE scheduled_transfers SET status='FAILED',last_error_code='INSUFFICIENT_FUNDS',updated_at=NOW(6) WHERE id=?",id);
            return;
        }
        // Conservative execution-day risk, including still-in-flight bank orders.
        var day=LocalDate.now(ZoneId.of("Asia/Shanghai"));
        var start=Timestamp.valueOf(day.atStartOfDay());
        var end=Timestamp.valueOf(day.plusDays(1).atStartOfDay());
        BigDecimal used=jdbc.queryForObject("""
          SELECT COALESCE(SUM(amount),0) FROM transfer_orders WHERE user_id=? AND created_at>=? AND created_at<?
             AND status IN ('PENDING_APPROVAL','AUTHORIZED','EXECUTING','SUCCESS','UNKNOWN')
          """,BigDecimal.class,owner,start,end);
        String needed=(used==null?BigDecimal.ZERO:used).add(amount).compareTo(new BigDecimal("1000.00"))>0
            ? "RED":"YELLOW";
        if(!"RED".equals(auth.get(0).get("covered_risk")) || !"DEMO_OTP".equals(auth.get(0).get("auth_method"))){
            fail(id,"PREAUTH_RISK_MISMATCH");return;
        }
        // Same database transaction: the funds port must use the EXISTING Day6
        // transaction service via a trusted internal execution path and be idempotent.
        jdbc.update("UPDATE scheduled_transfers SET status='PROCESSING',updated_at=NOW(6) WHERE id=?",id);
        var instruction=new Day7ScheduledFundsPort.Instruction(id,owner,sender,receiver,amount,remark,"SCHEDULE_"+id);
        var outcome=rail.executeAuthorized(instruction);
        if(outcome==null || !outcome.bankSuccess() || outcome.transferOrderId()<=0){
            jdbc.update("""
              UPDATE scheduled_transfers SET status='FAILED',last_error_code='SETTLEMENT_ADAPTER_NOT_CONNECTED',
              updated_at=NOW(6) WHERE id=?
              """,id);
            return;
        }
        Integer verified=jdbc.queryForObject("""
          SELECT COUNT(*) FROM transfer_orders WHERE id=? AND user_id=? AND sender_account_id=?
          AND receiver_account_id=? AND amount=? AND status='SUCCESS'
          """,Integer.class,outcome.transferOrderId(),owner,sender,receiver,amount);
        Integer legs=jdbc.queryForObject("""
            SELECT COUNT(*) FROM transactions WHERE transfer_order_id=? AND direction IN ('IN','OUT')
            """,Integer.class,outcome.transferOrderId());
        if(verified==null || verified!=1 || legs==null || legs!=2)
            throw new IllegalStateException("Bank transfer/ledger proof absent; rollback and reconcile");
        jdbc.update("""
          UPDATE scheduled_transfers SET status='SUCCESS',transfer_order_id=?,executed_at=UTC_TIMESTAMP(6),
             last_error_code=NULL,updated_at=NOW(6) WHERE id=?
          """,outcome.transferOrderId(),id);
        jdbc.update("INSERT INTO business_audit_events(actor_user_id,business_type,business_id,action,result) VALUES (?,'SCHEDULE',?,'EXECUTE','SUCCESS')",owner,Long.toString(id));
    }
    /** Invoked after failed transactional attempt has rolled back; no automatic retry. */
    @Transactional
    public void markUnknown(long id){
        jdbc.update("UPDATE scheduled_transfers SET status='UNKNOWN',last_error_code='EXECUTION_UNCERTAIN',updated_at=NOW(6) WHERE id=? AND status='SCHEDULED'",id);
    }
    private void fail(long id,String code){
        jdbc.update("UPDATE scheduled_transfers SET status='FAILED',last_error_code=?,updated_at=NOW(6) WHERE id=?",code,id);
    }
}
