package com.bankpilot.demo;

import org.springframework.stereotype.Service;
import org.springframework.jdbc.core.JdbcTemplate;

/** Only called by the DB-locked scheduled coordinator, never HTTP-exposed. */
@Service
public class Day7ScheduledFundsBankAdapter implements Day7ScheduledFundsPort {
    private final JdbcTemplate jdbc;
    private final TransferPrepareService prepare;
    private final TransferWorkflowService workflow;
    public Day7ScheduledFundsBankAdapter(JdbcTemplate jdbc,TransferPrepareService prepare,
            TransferWorkflowService workflow){
        this.jdbc=jdbc;this.prepare=prepare;this.workflow=workflow;
    }
    @Override
    public Outcome executeAuthorized(Instruction instruction){
        var payees=jdbc.query("""
            SELECT payee_id FROM scheduled_transfers WHERE id=? AND owner_user_id=?
               AND sender_account_id=? AND receiver_account_id=? AND status='PROCESSING'
            """,(rs,i)->rs.getLong(1),instruction.scheduleId(),instruction.ownerUserId(),
                instruction.senderAccountId(),instruction.receiverAccountId());
        if(payees.size()!=1)throw new IllegalStateException("Trusted schedule not found");
        var order=prepare.prepare(instruction.ownerUserId(),new TransferPrepareController.PrepareRequest(
             payees.get(0),instruction.amount().toPlainString(),instruction.requestId(),instruction.remark()));
        if(!"PENDING_APPROVAL".equals(order.status()))
            throw new IllegalStateException("Scheduled bank order is not new pending order");
        int linked=jdbc.update("""
            UPDATE scheduled_transfers SET transfer_order_id=?
            WHERE id=? AND status='PROCESSING' AND transfer_order_id IS NULL
            """,order.orderId(),instruction.scheduleId());
        if(linked!=1)throw new IllegalStateException("Schedule already linked to bank order");
        var finalOrder=workflow.executePreauthorizedSchedule(instruction.ownerUserId(),
            order.orderId(),instruction.scheduleId());
        return new Outcome(order.orderId(),"SUCCESS".equals(finalOrder.status()));
    }
}
