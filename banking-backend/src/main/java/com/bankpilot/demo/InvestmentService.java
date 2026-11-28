package com.bankpilot.demo;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;
import java.util.regex.Pattern;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/** D13 simulated investment ledger. Fixed illustrative NAV; never real investments. */
@Service
public class InvestmentService {
    private static final ZoneId CN = ZoneId.of("Asia/Shanghai");
    private static final Pattern QTY = Pattern.compile("[0-9]{1,6}(?:\\.[0-9]{1,2})?");
    private static final Pattern RID = Pattern.compile("[A-Za-z0-9_-]{8,64}");
    private static final BigDecimal LIMIT = new BigDecimal("100000.00");
    private final JdbcTemplate jdbc;

    public InvestmentService(JdbcTemplate jdbc) { this.jdbc = jdbc; }
    private static LocalDateTime now() { return LocalDateTime.now(CN); }
    private static ResponseStatusException bad(String reason) { return new ResponseStatusException(HttpStatus.BAD_REQUEST, reason); }
    private static ResponseStatusException conflict(String reason) { return new ResponseStatusException(HttpStatus.CONFLICT, reason); }

    public record Product(long productId, String code, String name, int riskLevel,
                          BigDecimal nav, boolean active, String description, String source) {}
    public record Profile(int riskLevel, String source) {}
    public record Position(long productId, String productName, BigDecimal units,
                           BigDecimal costBasis, BigDecimal nav, BigDecimal demoMarketValue, String source) {}
    public record OrderView(long orderId, long productId, String productName, String action,
                            BigDecimal units, BigDecimal amount, BigDecimal nav,
                            int riskLevel, String status, String source) {}
    private record Account(long id, BigDecimal balance) {}
    private record Quote(long id, BigDecimal nav, int risk, boolean active) {}
    private record Order(long id, long userId, long accountId, long productId,
                         String action, BigDecimal units, BigDecimal amount, BigDecimal nav,
                         int risk, String status, LocalDateTime createdAt) {}
    private record Holding(BigDecimal units, BigDecimal cost) {}

    private void lockUser(long uid) {
        var ids = jdbc.query("SELECT id FROM users WHERE id=? FOR UPDATE", (rs,i)->rs.getLong(1), uid);
        if (ids.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Demo user missing");
    }
    private Account account(long uid, boolean lock) {
        String sql = "SELECT id,balance FROM accounts WHERE user_id=? AND status='ACTIVE' ORDER BY id LIMIT 1" + (lock?" FOR UPDATE":"");
        var rows = jdbc.query(sql,(rs,i)->new Account(rs.getLong("id"),rs.getBigDecimal("balance")),uid);
        if (rows.isEmpty()) throw conflict("No active demo account");
        return rows.get(0);
    }
    private Quote quote(long pid) {
        var rows=jdbc.query("SELECT id,nav,risk_level,active FROM investment_products WHERE id=?",
            (rs,i)->new Quote(rs.getLong("id"),rs.getBigDecimal("nav"),rs.getInt("risk_level"),rs.getBoolean("active")),pid);
        if(rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Demo product missing");
        return rows.get(0);
    }
    private static BigDecimal units(String value) {
        if(value==null || !QTY.matcher(value).matches()) throw bad("units must be positive decimal with <=2 places");
        BigDecimal n = new BigDecimal(value);
        if(n.signum()<=0 || n.compareTo(new BigDecimal("10000"))>0) throw bad("units out of demo range");
        return n.setScale(2);
    }
    private static BigDecimal cash(BigDecimal nav, BigDecimal qty) {
        BigDecimal amount = nav.multiply(qty).setScale(2,RoundingMode.HALF_UP);
        if(amount.signum()<=0 || amount.compareTo(LIMIT)>0) throw bad("demo order amount out of range");
        return amount;
    }
    private Profile requireProfile(long uid) {
        var rows=jdbc.query("SELECT risk_level FROM investment_profiles WHERE user_id=?",
            (rs,i)->new Profile(rs.getInt(1),"JAVA_MYSQL_SIMULATED"),uid);
        if(rows.isEmpty()) throw conflict("Complete simulated suitability questionnaire first");
        return rows.get(0);
    }
    @Transactional(readOnly=true)
    public List<Product> products() {
        return jdbc.query("SELECT id,code,name,risk_level,nav,active,description FROM investment_products ORDER BY risk_level,id",
            (rs,i)->new Product(rs.getLong("id"),rs.getString("code"),rs.getString("name"),rs.getInt("risk_level"),
                rs.getBigDecimal("nav"),rs.getBoolean("active"),rs.getString("description"),"JAVA_MYSQL_SIMULATED"));
    }
    @Transactional(readOnly=true)
    public Profile profile(long uid) { return requireProfile(uid); }

    /** Three answers are 1..3; risk is restricted by the lowest tolerance. DEMO ONLY. */
    @Transactional
    public Profile assess(long uid, int lossTolerance, int horizon, int experience) {
        if(lossTolerance<1||lossTolerance>3||horizon<1||horizon>3||experience<1||experience>3)
            throw bad("each suitability answer must be 1..3");
        lockUser(uid);
        int risk = Math.min(lossTolerance,Math.min(horizon,experience));
        int updated=jdbc.update("UPDATE investment_profiles SET risk_level=?,assessed_at=? WHERE user_id=?",
            risk,Timestamp.valueOf(now()),uid);
        if(updated==0) jdbc.update("INSERT INTO investment_profiles(user_id,risk_level,assessed_at) VALUES(?,?,?)",
            uid,risk,Timestamp.valueOf(now()));
        return new Profile(risk,"JAVA_MYSQL_SIMULATED");
    }

    @Transactional(readOnly=true)
    public List<Position> portfolio(long uid) {
        return jdbc.query("""
            SELECT p.id, p.name, s.units, s.cost_basis, p.nav
            FROM investment_positions s JOIN investment_products p ON p.id=s.product_id
            WHERE s.user_id=? AND s.units>0 ORDER BY p.id
            """,(rs,i)->new Position(rs.getLong("id"),rs.getString("name"),rs.getBigDecimal("units"),
                 rs.getBigDecimal("cost_basis"),rs.getBigDecimal("nav"),
                 rs.getBigDecimal("nav").multiply(rs.getBigDecimal("units")).setScale(2,RoundingMode.HALF_UP),"JAVA_MYSQL_SIMULATED"),uid);
    }

    private Order order(long uid,long oid,boolean lock) {
        var rows=jdbc.query("""
            SELECT id,user_id,account_id,product_id,action,units,amount,nav_snapshot,risk_snapshot,status,created_at
            FROM investment_orders WHERE id=? AND user_id=?
            """+(lock?" FOR UPDATE":""),(rs,i)->new Order(rs.getLong("id"),rs.getLong("user_id"),
              rs.getLong("account_id"),rs.getLong("product_id"),rs.getString("action"),
              rs.getBigDecimal("units"),rs.getBigDecimal("amount"),rs.getBigDecimal("nav_snapshot"),
              rs.getInt("risk_snapshot"),rs.getString("status"),rs.getTimestamp("created_at").toLocalDateTime()),oid,uid);
        if(rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Demo order not found for user");
        return rows.get(0);
    }
    private OrderView view(long uid,long oid) {
        var rows=jdbc.query("""
            SELECT o.id,o.product_id,p.name,o.action,o.units,o.amount,o.nav_snapshot,o.risk_snapshot,o.status
            FROM investment_orders o JOIN investment_products p ON p.id=o.product_id
            WHERE o.id=? AND o.user_id=?
            """,(rs,i)->new OrderView(rs.getLong("id"),rs.getLong("product_id"),rs.getString("name"),
                rs.getString("action"),rs.getBigDecimal("units"),rs.getBigDecimal("amount"),
                rs.getBigDecimal("nav_snapshot"),rs.getInt("risk_snapshot"),rs.getString("status"),
                "JAVA_MYSQL_SIMULATED"),oid,uid);
        if(rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Demo order missing");
        return rows.get(0);
    }
    @Transactional(readOnly=true)
    public OrderView getOrder(long uid,long oid) { return view(uid,oid); }
    @Transactional(readOnly=true)
    public List<OrderView> orders(long uid) {
        return jdbc.query("""
            SELECT o.id,o.product_id,p.name,o.action,o.units,o.amount,o.nav_snapshot,o.risk_snapshot,o.status
            FROM investment_orders o JOIN investment_products p ON p.id=o.product_id
            WHERE o.user_id=? ORDER BY o.id DESC LIMIT 20
            """,(rs,i)->new OrderView(rs.getLong("id"),rs.getLong("product_id"),rs.getString("name"),
                rs.getString("action"),rs.getBigDecimal("units"),rs.getBigDecimal("amount"),
                rs.getBigDecimal("nav_snapshot"),rs.getInt("risk_snapshot"),rs.getString("status"),
                "JAVA_MYSQL_SIMULATED"),uid);
    }

    /** Prepare only; no debit, units transfer or ledger insert here. */
    @Transactional
    public OrderView prepare(long uid,long pid,String action,String qty,String requestId) {
        if(!"BUY".equals(action)&&!"REDEEM".equals(action)) throw bad("action must be BUY or REDEEM");
        if(requestId==null||!RID.matcher(requestId).matches()) throw bad("invalid idempotency key");
        BigDecimal n=units(qty);
        lockUser(uid);
        var previous=jdbc.query("SELECT id,product_id,action,units FROM investment_orders WHERE user_id=? AND request_id=? FOR UPDATE",
            (rs,i)->new Object[]{rs.getLong("id"),rs.getLong("product_id"),rs.getString("action"),rs.getBigDecimal("units")},uid,requestId);
        if(!previous.isEmpty()) {
            var old=previous.get(0);
            if((long)old[1]!=pid || !old[2].equals(action) || ((BigDecimal)old[3]).compareTo(n)!=0)
                throw conflict("idempotency key reused with different order");
            return view(uid,(long)old[0]);
        }
        Account a=account(uid,false);
        Quote p=quote(pid);
        if("BUY".equals(action)) {
            if(!p.active()) throw conflict("product not accepting new purchases");
            if(requireProfile(uid).riskLevel()<p.risk()) throw conflict("suitability risk level insufficient");
        }
        BigDecimal amount=cash(p.nav(),n);
        // No balance or holding mutation at preparation. Settlement rechecks everything.
        jdbc.update("""
            INSERT INTO investment_orders(user_id,account_id,product_id,action,units,nav_snapshot,amount,
              risk_snapshot,request_id,status,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,'PENDING_APPROVAL',?,?)
            """,uid,a.id(),pid,action,n,p.nav(),amount,p.risk(),requestId,
            Timestamp.valueOf(now()),Timestamp.valueOf(now()));
        Long oid=jdbc.queryForObject("SELECT id FROM investment_orders WHERE user_id=? AND request_id=?",Long.class,uid,requestId);
        if(oid==null) throw new IllegalStateException("Created order missing");
        return view(uid,oid);
    }

    private Holding holding(long uid,long pid) {
        var rows=jdbc.query("SELECT units,cost_basis FROM investment_positions WHERE user_id=? AND product_id=? FOR UPDATE",
            (rs,i)->new Holding(rs.getBigDecimal("units"),rs.getBigDecimal("cost_basis")),uid,pid);
        return rows.isEmpty()?new Holding(new BigDecimal("0.00"),new BigDecimal("0.00")):rows.get(0);
    }
    private void mark(long oid,String state) {
        jdbc.update("UPDATE investment_orders SET status=?,updated_at=? WHERE id=?",state,Timestamp.valueOf(now()),oid);
    }
    @Transactional
    public OrderView confirm(long uid,long oid, boolean confirmed) {
        lockUser(uid);
        Order order=order(uid,oid,true);
        if(!"PENDING_APPROVAL".equals(order.status())) return view(uid,oid); // terminal response, no repeat side effects
        if(!confirmed) { mark(oid,"CANCELLED"); return view(uid,oid); }
        if(order.createdAt().isBefore(now().minusMinutes(5))) { mark(oid,"EXPIRED"); return view(uid,oid); }
        Account acc=account(uid,true);
        if(acc.id()!=order.accountId()) throw conflict("source account changed");
        Quote p=quote(order.productId());
        if(p.risk()!=order.risk() || p.nav().compareTo(order.nav())!=0) {
            mark(oid,"EXPIRED"); return view(uid,oid); // stale quote; never silently reprice
        }
        if("BUY".equals(order.action()) && (!p.active() || requireProfile(uid).riskLevel()<p.risk()))
            throw conflict("purchase no longer suitable");
        Holding h=holding(uid,order.productId()); // same order of locks for buys/redeems
        BigDecimal cashDelta, unitsDelta, updatedUnits, updatedCost;
        if("BUY".equals(order.action())) {
            if(acc.balance().compareTo(order.amount())<0) { mark(oid,"FAILED"); return view(uid,oid); }
            cashDelta=order.amount().negate(); unitsDelta=order.units();
            updatedUnits=h.units().add(order.units());
            updatedCost=h.cost().add(order.amount());
        } else {
            if(h.units().compareTo(order.units())<0) { mark(oid,"FAILED"); return view(uid,oid); }
            cashDelta=order.amount(); unitsDelta=order.units().negate();
            updatedUnits=h.units().subtract(order.units());
            BigDecimal removedCost = updatedUnits.signum()==0 ? h.cost()
                : h.cost().multiply(order.units()).divide(h.units(),2,RoundingMode.HALF_UP);
            updatedCost=h.cost().subtract(removedCost);
        }
        // Bank balance + holding + unique ledger + SUCCESS share one SQL transaction.
        int count = jdbc.update("UPDATE accounts SET balance=balance+? WHERE id=? AND user_id=? AND status='ACTIVE' AND balance + ? >= 0",
            cashDelta,acc.id(),uid,cashDelta);
        if(count!=1) throw conflict("account debit rejected");
        var countPosition=jdbc.queryForObject("SELECT COUNT(*) FROM investment_positions WHERE user_id=? AND product_id=?",Long.class,uid,order.productId());
        if(countPosition==null||countPosition==0) {
            jdbc.update("INSERT INTO investment_positions(user_id,product_id,units,cost_basis) VALUES(?,?,?,?)",
                uid,order.productId(),updatedUnits,updatedCost);
        } else {
            jdbc.update("UPDATE investment_positions SET units=?,cost_basis=? WHERE user_id=? AND product_id=?",
                updatedUnits,updatedCost,uid,order.productId());
        }
        jdbc.update("""
            INSERT INTO investment_ledger(order_id,user_id,account_id,product_id,action,cash_delta,units_delta,created_at)
            VALUES(?,?,?,?,?,?,?,?)
            """,oid,uid,acc.id(),order.productId(),order.action(),cashDelta,unitsDelta,Timestamp.valueOf(now()));
        mark(oid,"SUCCESS");
        return view(uid,oid);
    }
}
