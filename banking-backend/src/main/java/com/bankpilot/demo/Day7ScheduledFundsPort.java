package com.bankpilot.demo;

import java.math.BigDecimal;

/**
 * SECURE INTEGRATION BOUNDARY, NOT AN IMPLEMENTED BANK TRANSFER.
 * Implement this adapter with the existing TransferWorkflowService's INTERNAL,
 * verified, transactional execution routine. Do not call a public /execute
 * endpoint or bypass Day6 OTP/approval rules.
 */
public interface Day7ScheduledFundsPort {
    record Instruction(long scheduleId,long ownerUserId,long senderAccountId,long receiverAccountId,
                       BigDecimal amount,String remark,String requestId) {}
    record Outcome(long transferOrderId,boolean bankSuccess) {}
    Outcome executeAuthorized(Instruction instruction);
}
