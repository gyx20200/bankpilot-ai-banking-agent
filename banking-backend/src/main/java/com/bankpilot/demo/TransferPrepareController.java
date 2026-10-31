package com.bankpilot.demo;

import java.math.BigDecimal;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/transfers")
public class TransferPrepareController {
    private final TransferPrepareService service;
    public TransferPrepareController(TransferPrepareService service) {
        this.service = service;
    }

    public record PrepareRequest(Long payeeId, String amount, String requestId, String remark) { }
    public record OrderView(long orderId, String payeeName, String accountMasked,
                            BigDecimal amount, String riskLevel, String status, String remark) { }

    @PostMapping("/prepare")
    @ResponseStatus(HttpStatus.CREATED)
    public OrderView prepare(@RequestBody PrepareRequest request) {
        return service.prepare(AuthenticatedUser.id(), request);
    }
}
