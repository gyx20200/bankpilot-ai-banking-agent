package com.bankpilot.demo;

import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.*;

/** Day7 contract: agent-service/app/banking_client.py /api/aa endpoints. */
@RestController
@RequestMapping("/api/aa")
public class Day7AaController {
    private final Day7AaService service;
    public Day7AaController(Day7AaService service) {this.service=service;}
    public record Prepare(List<String> participants,String amount,String splitMode,String reason,String requestId) {}
    public record RequestId(String requestId) {}
    public record Confirm(String requestId, Boolean confirmed, String otpCode) {}

    @PostMapping("/prepare")
    public Map<String,Object> prepare(@RequestBody Prepare body) {return service.prepare(AuthenticatedUser.id(),body);}
    @GetMapping("/outgoing")
    public List<Map<String,Object>> outgoing() {return service.outgoing(AuthenticatedUser.id());}
    @GetMapping("/inbox")
    public List<Map<String,Object>> inbox() {return service.inbox(AuthenticatedUser.id());}
    @GetMapping("/{id}")
    public Map<String,Object> get(@PathVariable long id) {return service.get(AuthenticatedUser.id(),id);}
    @PostMapping("/{id}/publish")
    public Map<String,Object> publish(@PathVariable long id,@RequestBody RequestId body) {return service.transition(AuthenticatedUser.id(),id,body,"PUBLISHED");}
    @PostMapping("/{id}/cancel-draft")
    public Map<String,Object> cancel(@PathVariable long id,@RequestBody RequestId body) {return service.transition(AuthenticatedUser.id(),id,body,"CANCELLED");}
    @GetMapping("/items/{id}/payment")
    public TransferWorkflowService.StatusView payment(@PathVariable long id) {return service.payment(AuthenticatedUser.id(),id);}
    @PostMapping("/items/{id}/payment/prepare")
    public TransferPrepareController.OrderView paymentPrepare(@PathVariable long id,@RequestBody RequestId body) {
        return service.paymentPrepare(AuthenticatedUser.id(),id,body);
    }
    @PostMapping("/items/{id}/otp/request")
    public TransferWorkflowService.OtpView otp(@PathVariable long id) {return service.otp(AuthenticatedUser.id(),id);}
    @PostMapping("/items/{id}/payment/confirm")
    public Map<String,Object> pay(@PathVariable long id,@RequestBody Confirm body) {
        Map<String,Object> result=service.pay(AuthenticatedUser.id(),id,body);
        if (!"PAID".equals(result.get("status")))
            throw new org.springframework.web.server.ResponseStatusException(org.springframework.http.HttpStatus.CONFLICT,
                "Bank transfer is not SUCCESS; inspect original payment order");
        return result;
    }
    @PostMapping("/items/{id}/decline")
    public Map<String,Object> decline(@PathVariable long id,@RequestBody RequestId body) {return service.decline(AuthenticatedUser.id(),id,body);}
}
