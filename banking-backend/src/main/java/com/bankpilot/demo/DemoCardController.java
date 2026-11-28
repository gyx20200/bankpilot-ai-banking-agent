package com.bankpilot.demo;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

/** D14 demo virtual cards. Never issue real payment credentials. */
@RestController
@RequestMapping("/api/demo/cards")
public class DemoCardController {
    private final DemoCardService cards;
    public DemoCardController(DemoCardService cards) {this.cards=cards;}
    public record PrepareRequest(String cardType, String requestId) {}
    public record Decision(Boolean confirmed) {}
    public record Restriction(String singleTransactionLimit, Boolean disableOnline, String requestId) {}

    @GetMapping
    public List<DemoCardService.CardView> list() {return cards.cards(AuthenticatedUser.id());}
    @GetMapping("/applications")
    public List<DemoCardService.ApplicationView> applications() {return cards.applications(AuthenticatedUser.id());}
    @GetMapping("/applications/{id}")
    public DemoCardService.ApplicationView application(@PathVariable long id) {
        return cards.application(AuthenticatedUser.id(),id);
    }
    @PostMapping("/applications/prepare")
    public DemoCardService.ApplicationView prepare(@RequestBody PrepareRequest body) {
        if(body==null) throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Request body required");
        return cards.prepare(AuthenticatedUser.id(),body.cardType(),body.requestId());
    }
    @PostMapping("/applications/{id}/confirm")
    public DemoCardService.ApplicationView confirm(@PathVariable long id,@RequestBody Decision body) {
        if(body==null || body.confirmed()==null)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Explicit confirmation required");
        return cards.confirm(AuthenticatedUser.id(),id,body.confirmed());
    }
    @PostMapping("/{id}/restrictions")
    public DemoCardService.CardView restrict(@PathVariable long id,@RequestBody Restriction body) {
        if(body==null || body.disableOnline()==null)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Restriction fields required");
        return cards.restrict(AuthenticatedUser.id(),id,body.singleTransactionLimit(),body.disableOnline(),body.requestId());
    }
}
