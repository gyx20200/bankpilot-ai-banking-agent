package com.bankpilot.demo;

import java.math.BigDecimal;
import java.security.SecureRandom;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.HexFormat;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/** Registered simulated-bank users; preserves the Day6 token format. */
@Service
public class Day7AuthService {
    private final JdbcTemplate jdbc;
    private final DemoTokenService tokens;
    private final BCryptPasswordEncoder passwords = new BCryptPasswordEncoder(12);
    private final SecureRandom random = new SecureRandom();
    private final BigDecimal initialBalance;
    private static final ZoneId ZONE = ZoneId.of("Asia/Shanghai");
    private static final String DUMMY_HASH = "$2a$12$abcdefghijklmnopqrstuuC0VvW9xU7sP16QH2I7DcdqiaZ1gMMo2";
    public record Profile(long userId,String username,String displayName,String phoneMasked) {}
    public record LoginResult(String token,String tokenType,long expiresInSeconds,String displayName) {}
    public record Registration(String status,long userId) {}
    private record LoginRow(long id,String name,String phone,String status,String username,
                            String hash,int attempts,LocalDateTime lockedUntil) {}

    public Day7AuthService(JdbcTemplate jdbc,DemoTokenService tokens,
            @Value("${bankpilot.day7.initial-balance:10000.00}") BigDecimal initialBalance) {
        this.jdbc=jdbc; this.tokens=tokens; this.initialBalance=initialBalance;
    }
    private static LocalDateTime now(){return LocalDateTime.now(ZONE);}
    private long nextId(String entity){
        var ids=jdbc.query("SELECT next_id FROM day7_id_sequences WHERE entity=? FOR UPDATE",
            (rs,i)->rs.getLong(1),entity);
        if(ids.size()!=1)throw new IllegalStateException("Day7 migration missing sequence "+entity);
        jdbc.update("UPDATE day7_id_sequences SET next_id=next_id+1 WHERE entity=?",entity);
        return ids.get(0);
    }
    @Transactional
    public Registration register(Day7AuthController.RegisterRequest b){
        if(b==null || b.username()==null || !b.username().matches("[A-Za-z0-9_]{3,32}")) bad("Username must be 3-32 ASCII chars");
        if(b.fullName()==null || b.fullName().isBlank() || b.fullName().trim().length()>80) bad("Invalid displayName");
        if(b.phone()==null || !b.phone().matches("1[3-9][0-9]{9}")) bad("Invalid phone");
        if(b.password()==null || b.password().length()<8 || b.password().length()>128) bad("Password length must be 8-128");
        if(initialBalance.signum()<0) throw new IllegalStateException("Invalid initial balance");
        try{
            long uid=nextId("users"); long aid=nextId("accounts");
            byte[] bytes=new byte[12];random.nextBytes(bytes);
            String accountNo="D7-"+HexFormat.of().formatHex(bytes).toUpperCase();
            jdbc.update("INSERT INTO users(id,display_name,phone,phone_verified,status) VALUES (?,?,?,0,'ACTIVE')",
                uid,b.fullName().trim(),b.phone());
            jdbc.update("INSERT INTO user_credentials(user_id,username,password_hash) VALUES (?,?,?)",
                uid,b.username(),passwords.encode(b.password()));
            jdbc.update("INSERT INTO accounts(id,user_id,account_no,balance,status) VALUES (?,?,?,?,'ACTIVE')",
                aid,uid,accountNo,initialBalance);
            jdbc.update("""
              INSERT INTO business_audit_events(actor_user_id,business_type,business_id,action,result)
              VALUES (?,'AUTH',?,'REGISTER','SUCCESS')
              """,uid,Long.toString(uid));
            return new Registration("REGISTERED",uid);
        }catch(DuplicateKeyException ex){throw new ResponseStatusException(HttpStatus.CONFLICT,"Username/phone/account already exists");}
    }
    /** On login failure, do NOT roll back failed_attempt_count/locked_until changes. */
    @Transactional(noRollbackFor=ResponseStatusException.class)
    public LoginResult login(Day7AuthController.LoginRequest b,String ip){
        String username=b==null||b.username()==null?"":b.username();
        String raw=b==null||b.password()==null?"":b.password();
        List<LoginRow> matches=jdbc.query("""
           SELECT u.id,u.display_name,u.phone,u.status,c.username,c.password_hash,
                  c.failed_login_count,c.locked_until
           FROM user_credentials c JOIN users u ON u.id=c.user_id WHERE c.username=? FOR UPDATE
           """,(rs,i)->new LoginRow(rs.getLong(1),rs.getString(2),rs.getString(3),rs.getString(4),
               rs.getString(5),rs.getString(6),rs.getInt(7),
               rs.getTimestamp(8)==null?null:rs.getTimestamp(8).toLocalDateTime()),username);
        var row=matches.isEmpty()?null:matches.get(0);
        boolean verified=passwords.matches(raw,row==null?DUMMY_HASH:row.hash());
        if(row==null) throw new ResponseStatusException(HttpStatus.UNAUTHORIZED,"Invalid credentials");
        if(row.lockedUntil()!=null && row.lockedUntil().isAfter(now()))
            throw new ResponseStatusException(HttpStatus.TOO_MANY_REQUESTS,"Account login temporarily locked");
        if(!verified || !"ACTIVE".equals(row.status())){
            int count=row.attempts()+1;
            jdbc.update("UPDATE user_credentials SET failed_login_count=?,locked_until=? WHERE user_id=?",
                count>=5?0:count,count>=5?java.sql.Timestamp.valueOf(now().plusMinutes(1)):null,row.id());
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED,"Invalid credentials");
        }
        jdbc.update("UPDATE user_credentials SET failed_login_count=0,locked_until=NULL WHERE user_id=?",row.id());
        var t=tokens.issue(new BankPrincipal(row.id(),row.name()));
        return new LoginResult(t.token(),"Bearer",t.expiresInSeconds(),
            row.name());
    }
    @Transactional(readOnly=true)
    public Profile profile(long userId){
        var rows=jdbc.query("""
            SELECT u.id,u.display_name,u.phone,c.username FROM users u
            LEFT JOIN user_credentials c ON c.user_id=u.id WHERE u.id=? AND u.status='ACTIVE'
            """,(rs,i)->new Profile(rs.getLong(1),rs.getString(4),rs.getString(2),maskPhone(rs.getString(3))),userId);
        if(rows.isEmpty())throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Active profile not found");
        return rows.get(0);
    }
    private static String maskPhone(String s){return s==null||s.length()<7?"":s.substring(0,3)+"****"+s.substring(s.length()-4);}
    private static void bad(String msg){throw new ResponseStatusException(HttpStatus.BAD_REQUEST,msg);}
}
