package com.bankpilot.demo;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.Statement;
import java.sql.Timestamp;
import org.springframework.beans.factory.annotation.Value;
import java.time.*;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/** Bank-owned durable scheduled authorizations. Execution is delegated to the safe settlement port. */
@Service
public class Day7ScheduledService {
    private static final ZoneId BUSINESS_ZONE=ZoneId.of("Asia/Shanghai");
    private final JdbcTemplate jdbc;
    private final DemoOtpVault otpVault;
    private final boolean otpDebug;
    public Day7ScheduledService(JdbcTemplate jdbc,DemoOtpVault otpVault,
            @Value("${bankpilot.demo.otp.debug-enabled:false}") boolean otpDebug){
        this.jdbc=jdbc; this.otpVault=otpVault; this.otpDebug=otpDebug;
    }
    private static LocalDateTime utc(){return LocalDateTime.now(ZoneOffset.UTC);}
    private static LocalDateTime businessNow(){return LocalDateTime.now(BUSINESS_ZONE);}
    private void lockUser(long user){
        var rows=jdbc.query("SELECT id FROM users WHERE id=? AND status='ACTIVE' FOR UPDATE",
            (rs,i)->rs.getLong(1),user);
        if(rows.size()!=1)bad("Inactive or unknown account owner");
    }
    private String risk(long user,BigDecimal amount){
        LocalDate date=LocalDate.now(BUSINESS_ZONE);
        BigDecimal pending=jdbc.queryForObject("""
            SELECT COALESCE(SUM(amount),0) FROM transfer_orders
            WHERE user_id=? AND created_at>=? AND created_at<?
              AND status IN ('PENDING_APPROVAL','AUTHORIZED','EXECUTING','SUCCESS','UNKNOWN')
            """,BigDecimal.class,user,Timestamp.valueOf(date.atStartOfDay()),
            Timestamp.valueOf(date.plusDays(1).atStartOfDay()));
        return (pending==null?BigDecimal.ZERO:pending).add(amount).compareTo(new BigDecimal("1000.00"))>0
             ? "RED":"YELLOW";
    }


    @Transactional
    public Map<String,Object> create(long user,Day7ScheduledController.CreateRequest b){
        if(b==null || b.payeeId()==null || b.payeeId()<=0 || b.requestId()==null ||
           !b.requestId().matches("[A-Za-z0-9_-]{8,64}")) bad("Invalid schedule or requestId");
        String remark=b.remark()==null?"":b.remark();
        if(remark.length()>80) bad("Remark too long");
        var amount=money(b.amount());
        OffsetDateTime dateTime;
        try {dateTime=OffsetDateTime.parse(b.executeAt());}
        catch(Exception ex){throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"executeAt must contain UTC offset, e.g. 2026-11-01T15:00:00+08:00");}
        Instant when=dateTime.toInstant().truncatedTo(java.time.temporal.ChronoUnit.SECONDS);
        if(!when.isAfter(Instant.now())) bad("Schedule time must be future");
        if(!dateTime.getOffset().equals(ZoneOffset.ofHours(8))) bad("executeAt must use +08:00");
        var sender=jdbc.query("SELECT id FROM accounts WHERE user_id=? AND status='ACTIVE' ORDER BY id LIMIT 1",
            (rs,n)->rs.getLong(1),user);
        var receiver=jdbc.query("""
            SELECT a.id FROM payees p JOIN accounts a ON a.id=p.payee_account_id
            WHERE p.user_id=? AND p.id=? AND a.status='ACTIVE'
            """,(rs,n)->rs.getLong(1),user,b.payeeId());
        if(sender.size()!=1 || receiver.size()!=1 || sender.get(0).equals(receiver.get(0)))
            throw new ResponseStatusException(HttpStatus.CONFLICT,"Invalid sender/receiver");
        String fingerprint=scope(user,sender.get(0),receiver.get(0),amount,when,remark);
        var duplicates=jdbc.queryForList("SELECT id,scope_hash FROM scheduled_transfers WHERE owner_user_id=? AND request_id=?",
            user,b.requestId());
        if(!duplicates.isEmpty()){
            var row=duplicates.get(0);
            if(!fingerprint.equals(row.get("scope_hash")))
                throw new ResponseStatusException(HttpStatus.CONFLICT,"requestId reused with different plan");
            return get(user,((Number)row.get("id")).longValue());
        }
        var key=new GeneratedKeyHolder();
        jdbc.update(con->{
            var ps=con.prepareStatement("""
              INSERT INTO scheduled_transfers(owner_user_id,sender_account_id,receiver_account_id,payee_id,
                 amount,remark,request_id,scope_hash,scheduled_at_utc,display_timezone,status,created_at,updated_at)
              VALUES(?,?,?,?,?,?,?,?,?,'Asia/Shanghai','PENDING_AUTH',NOW(6),NOW(6))
              """,Statement.RETURN_GENERATED_KEYS);
            ps.setLong(1,user);ps.setLong(2,sender.get(0));ps.setLong(3,receiver.get(0));ps.setLong(4,b.payeeId());
            ps.setBigDecimal(5,amount);ps.setString(6,remark);ps.setString(7,b.requestId());
            ps.setString(8,fingerprint);
            ps.setObject(9, LocalDateTime.ofInstant(when, ZoneOffset.UTC));
            return ps;
        },key);
        if(key.getKey()==null) throw new IllegalStateException("Schedule ID missing");
        jdbc.update("INSERT INTO business_audit_events(actor_user_id,business_type,business_id,action,result,trace_id) VALUES (?,'SCHEDULE',?,'CREATE','PENDING_AUTH',?)",
            user,key.getKey().toString(),b.requestId());
        return get(user,key.getKey().longValue());
    }

    @Transactional
    public Map<String,Object> requestOtp(long user,long id){
        var rows=jdbc.queryForList("SELECT * FROM scheduled_transfers WHERE id=? AND owner_user_id=? FOR UPDATE",id,user);
        if(rows.isEmpty())throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Schedule not found");
        var row=rows.get(0);
        if(!List.of("PENDING_AUTH").contains(row.get("status")))
            throw new ResponseStatusException(HttpStatus.CONFLICT,"Schedule not awaiting authorization");
        lockUser(user);
        var existing=jdbc.queryForList("SELECT failed_attempts FROM scheduled_otp_challenges WHERE schedule_id=? FOR UPDATE",id);
        if(!existing.isEmpty() && ((Number)existing.get(0).get("failed_attempts")).intValue()>=5)
            throw new ResponseStatusException(HttpStatus.CONFLICT,"OTP attempts exhausted");
        String code=otpVault.generate();
        byte[] salt=new byte[16];new java.security.SecureRandom().nextBytes(salt);
        String saltText=HexFormat.of().formatHex(salt);
        String digest=otpHash(saltText,code);
        jdbc.update("""
            INSERT INTO scheduled_otp_challenges(schedule_id,user_id,otp_salt,otp_hash,failed_attempts,expires_at)
            VALUES (?,?,?,?,0,?) ON DUPLICATE KEY UPDATE otp_salt=VALUES(otp_salt),
                otp_hash=VALUES(otp_hash),expires_at=VALUES(expires_at)
            """,id,user,saltText,digest,utc().plusMinutes(2));
        otpVault.store(-id,user,code,Instant.now().plusSeconds(120));
        return Map.of("scheduleId",Long.toString(id),"status","OTP_ISSUED","expiresInSeconds",120);
    }
    public Map<String,String> debugOtp(long user,long id,jakarta.servlet.http.HttpServletRequest request){
        if(!otpDebug || !("127.0.0.1".equals(request.getRemoteAddr()) ||
           "::1".equals(request.getRemoteAddr()) || "0:0:0:0:0:0:0:1".equals(request.getRemoteAddr())))
            throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Local demo OTP disabled");
        get(user,id);
        return Map.of("otp",otpVault.getDebugCode(-id,user),"warning","LOCAL_DEMO_ONLY_NOT_REAL_MFA");
    }
    @Transactional
    public Map<String,Object> authorize(long user,long id,Day7ScheduledController.AuthorizeRequest b){
        if(b==null || !Boolean.TRUE.equals(b.confirmed()) || !validRequest(b.requestId()))bad("Explicit confirmation and requestId required");
        var rows=jdbc.queryForList("SELECT * FROM scheduled_transfers WHERE id=? AND owner_user_id=? FOR UPDATE",id,user);
        if(rows.isEmpty())throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Schedule not found");
        var s=rows.get(0);
        if("SCHEDULED".equals(s.get("status")))return get(user,id);
        if(!List.of("PENDING_AUTH").contains(s.get("status")))
            throw new ResponseStatusException(HttpStatus.CONFLICT,"Schedule cannot be authorized");
        lockUser(user);
        var amount=(BigDecimal)s.get("amount");
        var due=dbDateTime(s.get("scheduled_at_utc"));
        if(!due.isAfter(utc()))
            throw new ResponseStatusException(HttpStatus.CONFLICT,"Schedule execution time already passed");
        // All scheduled transfers require their own short-lived DEMO OTP, regardless of amount.
        var codes=jdbc.queryForList("SELECT * FROM scheduled_otp_challenges WHERE schedule_id=? AND user_id=? FOR UPDATE",id,user);
        if(codes.size()!=1)throw new ResponseStatusException(HttpStatus.CONFLICT,"Request schedule OTP first");
        var code=codes.get(0);
        var expiry=dbDateTime(code.get("expires_at"));
        if(!expiry.isAfter(utc()) || ((Number)code.get("failed_attempts")).intValue()>=5)
            throw new ResponseStatusException(HttpStatus.CONFLICT,"OTP expired or exhausted");
        String candidate=b.otpCode()==null?"":b.otpCode();
        boolean correct=candidate.matches("[0-9]{6}") && MessageDigest.isEqual(
            otpHash((String)code.get("otp_salt"),candidate).getBytes(StandardCharsets.US_ASCII),
            ((String)code.get("otp_hash")).getBytes(StandardCharsets.US_ASCII));
        if(!correct){
            jdbc.update("UPDATE scheduled_otp_challenges SET failed_attempts=failed_attempts+1 WHERE schedule_id=?",id);
            // Return PENDING_AUTH to commit OTP failure counter; Agent must NOT advance.
            return get(user,id);
        }
        jdbc.update("DELETE FROM scheduled_otp_challenges WHERE schedule_id=?",id);
        otpVault.clear(-id);
        jdbc.update("""
          INSERT INTO scheduled_transfer_authorizations(schedule_id,user_id,auth_method,covered_risk,scope_hash,
             authorized_at,valid_until,status)
          VALUES (?,?,?,?,?,UTC_TIMESTAMP(6),?,'ACTIVE')
          ON DUPLICATE KEY UPDATE auth_method=VALUES(auth_method),covered_risk=VALUES(covered_risk),
             scope_hash=VALUES(scope_hash),authorized_at=VALUES(authorized_at),valid_until=VALUES(valid_until),
             revoked_at=NULL,status='ACTIVE'
          """,id,user,"DEMO_OTP","RED",
          s.get("scope_hash"),null);
        jdbc.update("UPDATE scheduled_transfers SET status='SCHEDULED',last_error_code=NULL,updated_at=NOW(6) WHERE id=?",id);
        jdbc.update("INSERT INTO business_audit_events(actor_user_id,business_type,business_id,action,result) VALUES (?,'SCHEDULE',?,'PREAUTHORIZE','SCHEDULED')",user,Long.toString(id));
        return get(user,id);
    }

    private static String otpHash(String salt,String code){
        try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
            .digest((salt+":"+code).getBytes(StandardCharsets.US_ASCII)));}
        catch(NoSuchAlgorithmException ex){throw new IllegalStateException(ex);}
    }
    @Transactional
    public Map<String,Object> cancel(long user,long id,Day7ScheduledController.RequestId request){
        if(request==null || !validRequest(request.requestId()))bad("Invalid requestId");
        int changed=jdbc.update("""
          UPDATE scheduled_transfers SET status='CANCELLED',updated_at=NOW(6)
          WHERE id=? AND owner_user_id=? AND status IN ('PENDING_AUTH','SCHEDULED')
          """,id,user);
        if(changed==1){
            jdbc.update("UPDATE scheduled_transfer_authorizations SET status='REVOKED',revoked_at=UTC_TIMESTAMP(6) WHERE schedule_id=? AND status='ACTIVE'",id);
            otpVault.clear(-id);
            jdbc.update("INSERT INTO business_audit_events(actor_user_id,business_type,business_id,action,result) VALUES (?,'SCHEDULE',?,'CANCEL','CANCELLED')",user,Long.toString(id));
            return get(user,id);
        }
        var old=get(user,id);
        if("CANCELLED".equals(old.get("status")))return old;
        throw new ResponseStatusException(HttpStatus.CONFLICT,"Schedule already executing or completed");
    }

    @Transactional(readOnly=true)
    public Map<String,Object> get(long user,long id){
        var rows=jdbc.queryForList("""
            SELECT s.*,p.payee_name,a.account_no FROM scheduled_transfers s
            JOIN payees p ON p.id=s.payee_id JOIN accounts a ON a.id=s.receiver_account_id
            WHERE s.id=? AND s.owner_user_id=?
            """,id,user);
        if(rows.isEmpty())throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Schedule not found");
        var s=rows.get(0);
        var due=dbDateTime(s.get("scheduled_at_utc")).toInstant(ZoneOffset.UTC);
        var view=new LinkedHashMap<String,Object>();
        view.put("scheduleId",Long.toString(id));
        view.put("payeeName",s.get("payee_name"));
        view.put("accountMasked",AccountMasker.mask((String)s.get("account_no")));
        view.put("amount",((BigDecimal)s.get("amount")).setScale(2).toPlainString());
        view.put("remark",s.get("remark"));
        view.put("executeAt",due.atOffset(ZoneOffset.UTC).atZoneSameInstant(BUSINESS_ZONE).toOffsetDateTime()
            .format(java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ssXXX")));
        view.put("status",s.get("status"));
        view.put("orderId",s.get("transfer_order_id")==null?null:String.valueOf(s.get("transfer_order_id")));
        view.put("failureReason",s.get("last_error_code"));
        return view;
    }
    @Transactional(readOnly=true)
    public List<Map<String,Object>> list(long user){
        var ids=jdbc.query("SELECT id FROM scheduled_transfers WHERE owner_user_id=? ORDER BY id DESC LIMIT 100",
            (rs,i)->rs.getLong(1),user);
        var result=new ArrayList<Map<String,Object>>();
        for(long id:ids)result.add(get(user,id));
        return result;
    }
    /** JdbcTemplate.queryForList may return LocalDateTime on MySQL and Timestamp on H2/other drivers. */
    static LocalDateTime dbDateTime(Object value){
        if(value instanceof LocalDateTime dt) return dt;
        if(value instanceof Timestamp ts) return ts.toLocalDateTime();
        throw new IllegalStateException("Unexpected SQL datetime value type: "
            +(value==null?"null":value.getClass().getName()));
    }

    private static boolean validRequest(String s){return s!=null && s.matches("[A-Za-z0-9_-]{8,64}");}

    private static BigDecimal money(String s){
        if(s==null || !s.matches("(?:0|[1-9][0-9]{0,8})(?:\\.[0-9]{1,2})?"))bad("Invalid amount");
        var amount=new BigDecimal(s).setScale(2,RoundingMode.UNNECESSARY);
        if(amount.signum()<=0 || amount.compareTo(new BigDecimal("1000000.00"))>0)bad("Invalid amount range");
        return amount;
    }
    static String scope(long owner,long sender,long recipient,BigDecimal amount,Instant due,String remark){
        var raw=owner+":"+sender+":"+recipient+":"+amount.toPlainString()+":"+due+":"+remark;
        try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(raw.getBytes(StandardCharsets.UTF_8)));}
        catch(NoSuchAlgorithmException ex){throw new IllegalStateException(ex);}
    }
    private static void bad(String reason){throw new ResponseStatusException(HttpStatus.BAD_REQUEST,reason);}
}
