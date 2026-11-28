package com.bankpilot.demo;

import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;
import java.util.UUID;
import java.util.regex.Pattern;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/** D14 DEMO-ONLY virtual card metadata. Never generates a PAN, CVV or payment token. */
@Service
public class DemoCardService {
    private static final ZoneId CN = ZoneId.of("Asia/Shanghai");
    private static final BigDecimal DAILY = new BigDecimal("3000.00");
    private static final BigDecimal SINGLE = new BigDecimal("1000.00");
    private static final Pattern REQUEST = Pattern.compile("[A-Za-z0-9_-]{8,64}");
    private final JdbcTemplate jdbc;
    public DemoCardService(JdbcTemplate jdbc) { this.jdbc = jdbc; }
    private static Timestamp now() { return Timestamp.valueOf(LocalDateTime.now(CN)); }
    private static ResponseStatusException bad(String text) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, text);
    }
    private static ResponseStatusException conflict(String text) {
        return new ResponseStatusException(HttpStatus.CONFLICT, text);
    }
    private static void requestId(String value) {
        if (value == null || !REQUEST.matcher(value).matches()) throw bad("Invalid requestId");
    }
    private void lockUser(long uid) {
        List<Long> ids = jdbc.query("SELECT id FROM users WHERE id=? FOR UPDATE", (rs,i)->rs.getLong(1), uid);
        if (ids.size()!=1) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Demo user missing");
    }
    private long activeAccount(long uid) {
        var ids = jdbc.query("SELECT id FROM accounts WHERE user_id=? AND status='ACTIVE' ORDER BY id LIMIT 1",
            (rs,i)->rs.getLong(1), uid);
        if (ids.isEmpty()) throw conflict("An active demo account is required");
        return ids.get(0);
    }
    public record CardView(long cardId, String cardAlias, String cardType, String status,
                           BigDecimal dailyCeiling, BigDecimal singleTransactionLimit,
                           boolean onlineEnabled, String source) {}
    public record ApplicationView(long applicationId, String status, String cardType,
                                  Long cardId, String source) {}
    private record Card(long cardId, BigDecimal daily, BigDecimal single, boolean online, String status) {}
    private record LimitEvent(long cardId, BigDecimal newSingle, boolean disableOnline) {}

    @Transactional(readOnly=true)
    public List<CardView> cards(long uid) {
        return jdbc.query("""
            SELECT id,card_alias,card_type,status,daily_ceiling,single_tx_limit,online_enabled
              FROM demo_virtual_cards WHERE user_id=? ORDER BY id DESC
            """, (rs,i)-> new CardView(rs.getLong(1),rs.getString(2),rs.getString(3),rs.getString(4),
                rs.getBigDecimal(5),rs.getBigDecimal(6),rs.getBoolean(7),"JAVA_MYSQL_DEMO_ONLY"), uid);
    }
    @Transactional(readOnly=true)
    public List<ApplicationView> applications(long uid) {
        return jdbc.query("""
            SELECT id,status,card_type,card_id FROM demo_card_applications
              WHERE user_id=? ORDER BY id DESC LIMIT 20
            """, (rs,i)->new ApplicationView(rs.getLong(1),rs.getString(2),rs.getString(3),
              rs.getObject(4)==null?null:rs.getLong(4),"JAVA_MYSQL_DEMO_ONLY"),uid);
    }
    private ApplicationView applicationView(long uid,long aid) {
        var rows = jdbc.query("""
            SELECT id,status,card_type,card_id FROM demo_card_applications WHERE id=? AND user_id=?
            """,(rs,i)->new ApplicationView(rs.getLong(1),rs.getString(2),rs.getString(3),
                  rs.getObject(4)==null?null:rs.getLong(4),"JAVA_MYSQL_DEMO_ONLY"),aid,uid);
        if (rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Application not found");
        return rows.get(0);
    }
    @Transactional(readOnly=true)
    public ApplicationView application(long uid,long aid) { return applicationView(uid,aid); }

    /** Request preparation is idempotent, and does NOT issue a card. */
    @Transactional
    public ApplicationView prepare(long uid,String kind,String rid) {
        if (!"VIRTUAL_DEBIT".equals(kind)) throw bad("Only virtual demo debit card is supported");
        requestId(rid);
        lockUser(uid);
        var old=jdbc.query("SELECT id,card_type FROM demo_card_applications WHERE user_id=? AND request_id=? FOR UPDATE",
            (rs,i)->new Object[]{rs.getLong(1),rs.getString(2)},uid,rid);
        if (!old.isEmpty()) {
            if (!kind.equals(old.get(0)[1])) throw conflict("requestId reused with different card type");
            return applicationView(uid,(long)old.get(0)[0]);
        }
        Long existing=jdbc.queryForObject("SELECT COUNT(*) FROM demo_virtual_cards WHERE user_id=?",Long.class,uid);
        if (existing!=null && existing>0) throw conflict("Demo user already has a virtual card");
        Long pending=jdbc.queryForObject("SELECT COUNT(*) FROM demo_card_applications WHERE user_id=? AND status='PENDING_APPROVAL'",Long.class,uid);
        if (pending!=null && pending>0) throw conflict("Resolve the original pending application first");
        long account=activeAccount(uid);
        jdbc.update("""
            INSERT INTO demo_card_applications(user_id,account_id,request_id,card_type,status,created_at,updated_at)
            VALUES(?,?,?,?,'PENDING_APPROVAL',?,?)
            """,uid,account,rid,kind,now(),now());
        Long aid=jdbc.queryForObject("SELECT id FROM demo_card_applications WHERE user_id=? AND request_id=?",Long.class,uid,rid);
        if (aid==null) throw new IllegalStateException("Card application missing after insert");
        return applicationView(uid,aid);
    }

    /** Only authenticated owner confirmation can issue one alias-only virtual card. */
    @Transactional
    public ApplicationView confirm(long uid,long aid,boolean confirmed) {
        lockUser(uid);
        var rows=jdbc.query("""
            SELECT id,account_id,status FROM demo_card_applications WHERE id=? AND user_id=? FOR UPDATE
            """,(rs,i)->new Object[]{rs.getLong(1),rs.getLong(2),rs.getString(3)},aid,uid);
        if (rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Application not found");
        String state=(String)rows.get(0)[2];
        if (!"PENDING_APPROVAL".equals(state)) return applicationView(uid,aid);
        if (!confirmed) {
            jdbc.update("UPDATE demo_card_applications SET status='CANCELLED',updated_at=? WHERE id=?",now(),aid);
            return applicationView(uid,aid);
        }
        Long count=jdbc.queryForObject("SELECT COUNT(*) FROM demo_virtual_cards WHERE user_id=?",Long.class,uid);
        if (count!=null && count>0) throw conflict("Demo card already exists");
        String alias="BP-VC-"+UUID.randomUUID().toString().replace("-","").substring(0,12).toUpperCase();
        jdbc.update("""
            INSERT INTO demo_virtual_cards(user_id,account_id,card_alias,card_type,status,
               daily_ceiling,single_tx_limit,online_enabled,issued_at)
            VALUES(?,?,?,'VIRTUAL_DEBIT','ACTIVE',?,?,TRUE,?)
            """,uid,(long)rows.get(0)[1],alias,DAILY,SINGLE,now());
        Long cid=jdbc.queryForObject("SELECT id FROM demo_virtual_cards WHERE card_alias=?",Long.class,alias);
        if(cid==null) throw new IllegalStateException("Created card not found");
        jdbc.update("UPDATE demo_card_applications SET status='ISSUED',card_id=?,updated_at=? WHERE id=?",cid,now(),aid);
        return applicationView(uid,aid);
    }
    private Card card(long uid,long cid) {
        var rows=jdbc.query("""
            SELECT id,daily_ceiling,single_tx_limit,online_enabled,status
            FROM demo_virtual_cards WHERE id=? AND user_id=? FOR UPDATE
            """,(rs,i)->new Card(rs.getLong(1),rs.getBigDecimal(2),rs.getBigDecimal(3),
                   rs.getBoolean(4),rs.getString(5)),cid,uid);
        if(rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Card not found");
        return rows.get(0);
    }
    private CardView getCard(long uid,long cid) {
        return cards(uid).stream().filter(c->c.cardId()==cid).findFirst()
            .orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND,"Card not found"));
    }
    /** D14 only NARROWS the local demo rule; D15 handles limit increases and card state changes. */
    @Transactional
    public CardView restrict(long uid,long cid,String newLimit,boolean disableOnline,String rid) {
        requestId(rid);
        if(newLimit==null || !newLimit.matches("[0-9]{1,6}(?:\\.[0-9]{1,2})?")) throw bad("singleTransactionLimit must be positive decimal");
        BigDecimal proposed=new BigDecimal(newLimit).setScale(2);
        if(proposed.signum()<=0) throw bad("singleTransactionLimit must be positive");
        lockUser(uid);
        // Verify the card owner BEFORE checking historical request IDs.
        Card existing=card(uid,cid);
        var prior=jdbc.query("""
            SELECT card_id,new_single_limit,disable_online FROM demo_card_limit_events
             WHERE user_id=? AND request_id=? FOR UPDATE
            """,(rs,i)->new LimitEvent(rs.getLong(1),rs.getBigDecimal(2),rs.getBoolean(3)),uid,rid);
        if(!prior.isEmpty()) {
            LimitEvent e=prior.get(0);
            if(e.cardId()!=cid || e.newSingle().compareTo(proposed)!=0 || e.disableOnline()!=disableOnline)
                throw conflict("requestId reused with different restriction");
            return getCard(uid,cid);
        }
        if(!"ACTIVE".equals(existing.status())) throw conflict("Card state does not allow D14 restrictions");
        if(proposed.compareTo(existing.single())>0 || proposed.compareTo(existing.daily())>0)
            throw conflict("D14 cannot increase the existing single-transaction limit");
        jdbc.update("""
            UPDATE demo_virtual_cards SET single_tx_limit=?,
              online_enabled=CASE WHEN ? THEN FALSE ELSE online_enabled END
              WHERE id=? AND user_id=?
            """,proposed,disableOnline,cid,uid);
        jdbc.update("""
            INSERT INTO demo_card_limit_events(user_id,card_id,request_id,old_single_limit,
                 new_single_limit,disable_online,created_at) VALUES(?,?,?,?,?,?,?)
            """,uid,cid,rid,existing.single(),proposed,disableOnline,now());
        return getCard(uid,cid);
    }
}
