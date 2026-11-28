package com.bankpilot.demo;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

/** All endpoints require the existing Spring bearer identity. Demo-only amounts. */
@RestController
@RequestMapping("/api/demo/investments")
public class InvestmentController {
    private final InvestmentService service;
    public InvestmentController(InvestmentService service) { this.service=service; }
    public record Assessment(int lossTolerance,int horizon,int experience) {}
    public record Prepare(long productId,String action,String units,String requestId) {}
    public record Decision(Boolean confirmed) {}

    @GetMapping("/products")
    public List<InvestmentService.Product> products() { AuthenticatedUser.id(); return service.products(); }
    @GetMapping("/profile")
    public InvestmentService.Profile profile() { return service.profile(AuthenticatedUser.id()); }
    @PostMapping("/profile/assess")
    public InvestmentService.Profile assess(@RequestBody Assessment body) {
        if(body==null) throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"assessment required");
        return service.assess(AuthenticatedUser.id(),body.lossTolerance(),body.horizon(),body.experience());
    }
    @GetMapping("/portfolio")
    public List<InvestmentService.Position> portfolio() { return service.portfolio(AuthenticatedUser.id()); }
    @GetMapping("/orders")
    public List<InvestmentService.OrderView> orders() { return service.orders(AuthenticatedUser.id()); }
    @GetMapping("/orders/{id}")
    public InvestmentService.OrderView order(@PathVariable long id) { return service.getOrder(AuthenticatedUser.id(),id); }
    @PostMapping("/orders/prepare")
    public InvestmentService.OrderView prepare(@RequestBody Prepare body) {
        if(body==null) throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"order required");
        return service.prepare(AuthenticatedUser.id(),body.productId(),body.action(),body.units(),body.requestId());
    }
    @PostMapping("/orders/{id}/confirm")
    public InvestmentService.OrderView confirm(@PathVariable long id,@RequestBody Decision body) {
        if(body==null||body.confirmed()==null)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"explicit confirmed boolean required");
        return service.confirm(AuthenticatedUser.id(),id,body.confirmed());
    }
}
