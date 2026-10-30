package com.bankpilot.demo;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.Statement;
import java.time.LocalDateTime;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/** Draft -> published -> separate authenticated payer approvals. Only bank SUCCESS makes PAID. */
@Service
public class Day7AaService {
    private final JdbcTemplate jdbc;
    private final Day7RecipientService recipients;
    private final TransferPrepareService prepare;
    private final TransferWorkflowService workflow;
    public Day7AaService(JdbcTemplate jdbc, Day7RecipientService recipients,
                          TransferPrepareService prepare, TransferWorkflowService workflow) {
        this.jdbc=jdbc;this.recipients=recipients;this.prepare=prepare;this.workflow=workflow;
    }
    private record Payer(long userId,String name,BigDecimal amount){}
    private record Item(long id,long collectionId,long owner,long payer,BigDecimal amount,String status,Long orderId,String collectionStatus){}

    @Transactional
    public Map<String,Object> prepare(long user,Day7AaController.Prepare request){
        if(request==null || !requestId(request.requestId()) || request.participants()==null ||
            request.participants().isEmpty() || request.participants().size()>10 ||
            !List.of("total_with_self","per_person").contains(request.splitMode())) bad("Invalid AA draft");
        String reason=request.reason()==null?"":request.reason().trim();
        if(reason.length()>80)bad("Reason exceeds 80 characters");
        BigDecimal source=money(request.amount());
        lockUser(user);
        Set<Long> seen=new HashSet<>();
        List<Payer> payers=new ArrayList<>();
        for(String name:request.participants()){
            if(name==null || name.isBlank() || !name.equals(name.trim()) || name.length()>80)bad("Invalid participant");
            String field=name.matches("1[3-9][0-9]{9}")?"u.phone":"u.display_name";
            var targets=jdbc.query("""
                SELECT u.id,u.display_name FROM users u JOIN accounts a ON a.user_id=u.id
                WHERE u.id<>? AND u.status='ACTIVE' AND a.status='ACTIVE' AND
                """+field+"=?",(rs,i)->Map.entry(rs.getLong(1),rs.getString(2)),user,name);
            if(targets.size()!=1 || !seen.add(targets.get(0).getKey()))conflict("AA recipient ambiguous or not registered");
            payers.add(new Payer(targets.get(0).getKey(),targets.get(0).getValue(),BigDecimal.ZERO));
        }
        int n=payers.size();
        BigDecimal self=BigDecimal.ZERO.setScale(2);
        List<BigDecimal> parts=new ArrayList<>();
        if("per_person".equals(request.splitMode())){
            for(int i=0;i<n;i++)parts.add(source);
        }else{
            long cents=source.movePointRight(2).longValueExact();
            long base=cents/(n+1),extra=cents%(n+1);
            for(int i=0;i<n;i++)parts.add(BigDecimal.valueOf(base+(i<extra?1:0),2));
            self=BigDecimal.valueOf(base+(n<extra?1:0),2);
        }
        for(int i=0;i<n;i++){
            if(parts.get(i).signum()<=0)bad("AA amount too small to split");
            Payer p=payers.get(i);payers.set(i,new Payer(p.userId(),p.name(),parts.get(i)));
        }
        BigDecimal requested=parts.stream().reduce(BigDecimal.ZERO,BigDecimal::add);
        BigDecimal total=requested.add(self);
        String fingerprint=sha(String.join("\u001e",request.participants())+"|"+source+"|"+request.splitMode()+"|"+reason);
        var previous=jdbc.query("SELECT id,request_fingerprint FROM aa_collections WHERE initiator_user_id=? AND request_id=?",
            (rs,i)->Map.entry(rs.getLong(1),rs.getString(2)),user,request.requestId());
        if(!previous.isEmpty()){
            if(!fingerprint.equals(previous.get(0).getValue()))conflict("AA requestId reused with different payload");
            return get(user,previous.get(0).getKey());
        }
        var key=new GeneratedKeyHolder();
        final BigDecimal ownShare=self,totalAmount=total,requiredAmount=requested;
        jdbc.update(c->{var ps=c.prepareStatement("""
            INSERT INTO aa_collections(initiator_user_id,request_id,request_fingerprint,split_mode,reason,
                total_amount,self_amount,requested_amount,status,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,'DRAFT',NOW(6),NOW(6))
            """,Statement.RETURN_GENERATED_KEYS);
            ps.setLong(1,user);ps.setString(2,request.requestId());ps.setString(3,fingerprint);
            ps.setString(4,request.splitMode());ps.setString(5,reason);ps.setBigDecimal(6,totalAmount);
            ps.setBigDecimal(7,ownShare);ps.setBigDecimal(8,requiredAmount);return ps;},key);
        if(key.getKey()==null)throw new IllegalStateException("AA ID missing");
        long cid=key.getKey().longValue();
        for(Payer p:payers)jdbc.update("""
            INSERT INTO aa_collection_items(collection_id,payer_user_id,amount,status,created_at,updated_at)
            VALUES(?,?,?,'PENDING',NOW(6),NOW(6))
            """,cid,p.userId(),p.amount());
        audit(user,"AA",cid,"PREPARE","DRAFT",request.requestId());
        return get(user,cid);
    }

    @Transactional
    public Map<String,Object> transition(long user,long id,Day7AaController.RequestId req,String desired){
        validate(req);
        lockUser(user);
        var rows=jdbc.queryForList("SELECT status FROM aa_collections WHERE id=? AND initiator_user_id=? FOR UPDATE",id,user);
        if(rows.isEmpty())notFound();
        String current=(String)rows.get(0).get("status");
        if(current.equals(desired))return get(user,id);
        if(!"DRAFT".equals(current))conflict("AA draft was already resolved");
        jdbc.update("UPDATE aa_collections SET status=?,updated_at=NOW(6) WHERE id=?",desired,id);
        audit(user,"AA",id,desired,desired,req.requestId());
        return get(user,id);
    }

    @Transactional
    public TransferPrepareController.OrderView paymentPrepare(long user,long itemId,Day7AaController.RequestId req){
        validate(req);lockUser(user);
        Item item=item(user,itemId,true);
        if(!List.of("PUBLISHED","PARTIAL").contains(item.collectionStatus()))conflict("AA not published");
        if(item.orderId()!=null){
            if(!"PAYING".equals(item.status()))conflict("AA item already resolved");
            return preparedOrder(user,item.orderId());
        }
        if(!"PENDING".equals(item.status()))conflict("AA item already resolved");
        var payee=recipients.ensurePayee(user,item.owner());
        // A fixed bank idempotency key derived from the AA item, not caller-provided.
        var order=prepare.prepare(user,new TransferPrepareController.PrepareRequest(
            payee.id(),item.amount().toPlainString(),"AAITEM_"+itemId,"AA request #"+item.collectionId()));
        if(!"PENDING_APPROVAL".equals(order.status()))conflict("AA transfer not awaiting approval");
        int updated=jdbc.update("UPDATE aa_collection_items SET transfer_order_id=?,status='PAYING',updated_at=NOW(6) WHERE id=? AND status='PENDING'",
            order.orderId(),itemId);
        if(updated!=1)conflict("AA payment racing with another action");
        audit(user,"AA",itemId,"PAY_PREPARE","PAYING",req.requestId());
        return order;
    }

    @Transactional(readOnly=true)
    public TransferWorkflowService.StatusView payment(long user,long itemId){
        Item item=item(user,itemId,false);
        if(item.orderId()==null)notFound();
        return workflow.status(user,item.orderId());
    }
    @Transactional
    public TransferWorkflowService.OtpView otp(long user,long itemId){
        Item item=item(user,itemId,true);
        if(!"PAYING".equals(item.status()) || item.orderId()==null)conflict("AA payment not awaiting OTP");
        return workflow.requestOtp(user,item.orderId());
    }

    @Transactional
    public Map<String,Object> pay(long user,long itemId,Day7AaController.Confirm req){
        if(req==null || !requestId(req.requestId()) || !Boolean.TRUE.equals(req.confirmed()))bad("Explicit payer confirmation required");
        lockUser(user);
        Item item=item(user,itemId,true);
        if("PAID".equals(item.status()))return itemView(user,itemId);
        if(!"PAYING".equals(item.status()) || item.orderId()==null)conflict("AA payment not prepared");
        var current=workflow.status(user,item.orderId());
        if("PENDING_APPROVAL".equals(current.status())){
            workflow.authorize(user,item.orderId(),true,req.otpCode());
            current=workflow.status(user,item.orderId());
        }
        if("AUTHORIZED".equals(current.status()))current=workflow.execute(user,item.orderId());
        // If OTP failed or risk upgraded: commit its security attempts and return a non-PAID view.
        if(!"SUCCESS".equals(current.status()))return itemView(user,itemId);
        int legs=jdbc.queryForObject("SELECT COUNT(*) FROM transactions WHERE transfer_order_id=? AND direction IN ('IN','OUT')",Integer.class,item.orderId());
        if(legs!=2)throw new IllegalStateException("AA bank ledger proof absent; rollback funds");
        int updated=jdbc.update("UPDATE aa_collection_items SET status='PAID',paid_at=NOW(6),updated_at=NOW(6) WHERE id=? AND status='PAYING'",itemId);
        if(updated!=1)throw new IllegalStateException("AA paid state race; rollback funds");
        audit(user,"AA",itemId,"PAY_EXECUTE","PAID",req.requestId());
        return itemView(user,itemId);
    }
    @Transactional
    public Map<String,Object> decline(long user,long itemId,Day7AaController.RequestId req){
        validate(req);lockUser(user);
        Item item=item(user,itemId,true);
        if("DECLINED".equals(item.status()))return itemView(user,itemId);
        if(!List.of("PENDING","PAYING").contains(item.status()))conflict("AA item cannot be declined");
        if(item.orderId()!=null){
            var view=workflow.cancel(user,item.orderId());
            if(!"CANCELLED".equals(view.status()))conflict("Bank order not cancelled");
        }
        jdbc.update("UPDATE aa_collection_items SET status='DECLINED',updated_at=NOW(6) WHERE id=?",itemId);
        audit(user,"AA",itemId,"DECLINE","DECLINED",req.requestId());
        return itemView(user,itemId);
    }

    @Transactional
    public List<Map<String,Object>> outgoing(long user){
        reconcileForUser(user);
        List<Long> ids=jdbc.query("""
            SELECT id FROM aa_collections WHERE initiator_user_id=? AND status NOT IN ('DRAFT','CANCELLED')
            ORDER BY id DESC LIMIT 100
            """,(rs,i)->rs.getLong(1),user);
        List<Map<String,Object>> result=new ArrayList<>();
        for(long id:ids)result.add(get(user,id));
        return result;
    }
    @Transactional
    public List<Map<String,Object>> inbox(long user){
        reconcileForUser(user);
        return jdbc.query("""
            SELECT i.id,c.id,c.initiator_user_id,u.display_name,c.reason,i.amount,i.status,i.transfer_order_id
            FROM aa_collection_items i JOIN aa_collections c ON c.id=i.collection_id
            JOIN users u ON u.id=c.initiator_user_id
            WHERE i.payer_user_id=? AND c.status NOT IN ('DRAFT','CANCELLED')
            ORDER BY i.id DESC LIMIT 100
            """,(rs,i)->{
                var out=new LinkedHashMap<String,Object>();
                out.put("itemId",Long.toString(rs.getLong(1)));out.put("collectionId",Long.toString(rs.getLong(2)));
                out.put("initiatorId",rs.getLong(3));out.put("initiatorName",rs.getString(4));
                out.put("reason",rs.getString(5));out.put("amount",amount(rs.getBigDecimal(6)));
                out.put("status",rs.getString(7));out.put("transferOrderId",rs.getObject(8)==null?null:Long.toString(rs.getLong(8)));
                return out;},user);
    }
    @Transactional
    public Map<String,Object> get(long user,long id){
        reconcileForUser(user);
        var main=jdbc.queryForList("SELECT * FROM aa_collections WHERE id=? AND initiator_user_id=?",id,user);
        if(main.isEmpty())notFound();
        var c=main.get(0);
        var items=jdbc.query("""
            SELECT i.id,i.payer_user_id,u.display_name,i.amount,i.status,i.transfer_order_id
            FROM aa_collection_items i JOIN users u ON u.id=i.payer_user_id
            WHERE i.collection_id=? ORDER BY i.id
            """,(rs,i)->{
                var out=new LinkedHashMap<String,Object>();
                out.put("itemId",Long.toString(rs.getLong(1)));out.put("collectionId",Long.toString(id));
                out.put("payerId",rs.getLong(2));out.put("payerName",rs.getString(3));
                out.put("amount",amount(rs.getBigDecimal(4)));out.put("status",rs.getString(5));
                out.put("transferOrderId",rs.getObject(6)==null?null:Long.toString(rs.getLong(6)));
                return out;},id);
        String state=(String)c.get("status");
        long paid=items.stream().filter(x->"PAID".equals(x.get("status"))).count();
        if(List.of("PUBLISHED","PARTIAL","COMPLETED").contains(state))state=paid==items.size()?"COMPLETED":paid>0?"PARTIAL":"PUBLISHED";
        BigDecimal received=jdbc.queryForObject("SELECT COALESCE(SUM(amount),0) FROM aa_collection_items WHERE collection_id=? AND status='PAID'",BigDecimal.class,id);
        String ownerName=jdbc.queryForObject("SELECT display_name FROM users WHERE id=?",String.class,user);
        var out=new LinkedHashMap<String,Object>();
        out.put("collectionId",Long.toString(id));out.put("initiatorId",user);out.put("initiatorName",ownerName);
        out.put("status",state);out.put("splitMode",c.get("split_mode"));out.put("reason",c.get("reason"));
        out.put("totalAmount",amount((BigDecimal)c.get("total_amount")));
        out.put("selfAmount",amount((BigDecimal)c.get("self_amount")));
        out.put("requestedAmount",amount((BigDecimal)c.get("requested_amount")));
        out.put("receivedAmount",amount(received));out.put("items",items);
        return out;
    }
    @Transactional(readOnly=true)
    public Map<String,Object> itemView(long user,long id){
        Item row=item(user,id,false);
        var m=new LinkedHashMap<String,Object>();m.put("itemId",Long.toString(id));
        m.put("collectionId",Long.toString(row.collectionId()));
        m.put("payerId",user);m.put("amount",amount(row.amount()));m.put("status",row.status());
        m.put("transferOrderId",row.orderId()==null?null:Long.toString(row.orderId()));return m;
    }
    private Item item(long user,long id,boolean lock){
        var rows=jdbc.query("""
            SELECT i.id,i.collection_id,c.initiator_user_id,i.payer_user_id,i.amount,i.status,
                   i.transfer_order_id,c.status
            FROM aa_collection_items i JOIN aa_collections c ON c.id=i.collection_id
            WHERE i.id=? AND i.payer_user_id=?
            """+(lock?" FOR UPDATE":""),(rs,i)->new Item(rs.getLong(1),rs.getLong(2),rs.getLong(3),rs.getLong(4),
              rs.getBigDecimal(5),rs.getString(6),rs.getObject(7)==null?null:rs.getLong(7),rs.getString(8)),id,user);
        if(rows.isEmpty())notFound();return rows.get(0);
    }
    private TransferPrepareController.OrderView preparedOrder(long user,long orderId){
        var rows=jdbc.query("""
            SELECT o.id,p.payee_name,a.account_no,o.amount,o.risk_level,o.status,o.remark
            FROM transfer_orders o JOIN payees p ON p.id=o.payee_id
            JOIN accounts a ON a.id=o.receiver_account_id WHERE o.id=? AND o.user_id=?
            """,(rs,i)->new TransferPrepareController.OrderView(rs.getLong(1),rs.getString(2),
              AccountMasker.mask(rs.getString(3)),rs.getBigDecimal(4),rs.getString(5),rs.getString(6),rs.getString(7)),orderId,user);
        if(rows.isEmpty())notFound();return rows.get(0);
    }
    /** Reconcile a payment completed via a separate Day6 execute HTTP call. SQL verifies both ledger legs. */
    private void reconcileForUser(long user){
        jdbc.update("""
            UPDATE aa_collection_items i JOIN aa_collections c ON c.id=i.collection_id
            JOIN transfer_orders t ON t.id=i.transfer_order_id
            JOIN accounts a ON a.id=t.receiver_account_id
            SET i.status='PAID',i.paid_at=NOW(6),i.updated_at=NOW(6)
            WHERE i.status='PAYING' AND (i.payer_user_id=? OR c.initiator_user_id=?)
              AND t.user_id=i.payer_user_id AND a.user_id=c.initiator_user_id
              AND t.amount=i.amount AND t.status='SUCCESS'
              AND 2=(SELECT COUNT(*) FROM transactions tr WHERE tr.transfer_order_id=t.id)
            """,user,user);
        jdbc.update("""
            UPDATE aa_collection_items i JOIN aa_collections c ON c.id=i.collection_id
            JOIN transfer_orders t ON t.id=i.transfer_order_id
            SET i.status='FAILED',i.updated_at=NOW(6)
            WHERE i.status='PAYING' AND (i.payer_user_id=? OR c.initiator_user_id=?)
              AND t.status IN ('FAILED','CANCELLED')
            """,user,user);
    }
    private void lockUser(long user){
        var rows=jdbc.query("SELECT id FROM users WHERE id=? AND status='ACTIVE' FOR UPDATE",(rs,i)->rs.getLong(1),user);
        if(rows.isEmpty())notFound();
    }
    private static void validate(Day7AaController.RequestId r){if(r==null||!requestId(r.requestId()))bad("Invalid requestId");}
    private static boolean requestId(String s){return s!=null && s.matches("[A-Za-z0-9_-]{8,64}");}
    private static BigDecimal money(String raw){
        if(raw==null || !raw.matches("(?:0|[1-9][0-9]{0,8})(?:\\.[0-9]{1,2})?"))bad("Invalid amount");
        var v=new BigDecimal(raw).setScale(2,RoundingMode.UNNECESSARY);
        if(v.signum()<=0 || v.compareTo(new BigDecimal("1000000"))>0)bad("Amount outside demo range");
        return v;
    }
    private static String amount(BigDecimal value){return value.setScale(2,RoundingMode.UNNECESSARY).toPlainString();}
    private void audit(long actor,String type,long id,String action,String result,String trace){
        jdbc.update("""
            INSERT INTO business_audit_events(actor_user_id,business_type,business_id,action,result,trace_id)
            VALUES(?,?,?,?,?,?)
            """,actor,type,Long.toString(id),action,result,trace);
    }
    private static String sha(String v){
        try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(v.getBytes(StandardCharsets.UTF_8)));}
        catch(NoSuchAlgorithmException ex){throw new IllegalStateException(ex);}
    }
    private static void bad(String why){throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY,why);}
    private static void conflict(String why){throw new ResponseStatusException(HttpStatus.CONFLICT,why);}
    private static void notFound(){throw new ResponseStatusException(HttpStatus.NOT_FOUND,"AA request not found for user");}
}
