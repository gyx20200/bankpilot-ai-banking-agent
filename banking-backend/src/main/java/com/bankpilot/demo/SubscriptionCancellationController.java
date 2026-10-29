package com.bankpilot.demo;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

/** Day6: Explicit human approval for BANK-SIDE simulated debit authorization cancellation. */
@RestController
@RequestMapping("/api/subscription-cancellations")
public class SubscriptionCancellationController {
    private final SubscriptionCancellationService service;

    public SubscriptionCancellationController(SubscriptionCancellationService service) {
        this.service = service;
    }

    public record PrepareRequest(Long subscriptionId, String requestId, String workflowId) { }
    public record AuthorizeRequest(Boolean confirmed) { }

    @PostMapping("/prepare")
    @ResponseStatus(HttpStatus.CREATED)
    public SubscriptionCancellationService.OrderView prepare(@RequestBody PrepareRequest request) {
        return service.prepare(AuthenticatedUser.id(), request);
    }

    @GetMapping("/{orderId}")
    public SubscriptionCancellationService.OrderView status(@PathVariable long orderId) {
        return service.status(AuthenticatedUser.id(), orderId);
    }

    @PostMapping("/{orderId}/authorize")
    public SubscriptionCancellationService.OrderView authorize(@PathVariable long orderId,
                                                                @RequestBody AuthorizeRequest request) {
        if (request == null || request.confirmed() == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "confirmed must be true or false");
        }
        return service.authorize(AuthenticatedUser.id(), orderId, request.confirmed());
    }

    @PostMapping("/{orderId}/execute")
    public SubscriptionCancellationService.OrderView execute(@PathVariable long orderId) {
        return service.execute(AuthenticatedUser.id(), orderId);
    }
}
