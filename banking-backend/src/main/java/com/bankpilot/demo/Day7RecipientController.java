package com.bankpilot.demo;

import org.springframework.web.bind.annotation.*;
import java.util.List;

@RestController
@RequestMapping("/api/transfers/recipients")
public class Day7RecipientController {
    private final Day7RecipientService service;
    public Day7RecipientController(Day7RecipientService service) { this.service=service; }
    public record ResolveRequest(String lookupType, String query) {}
    public record ConfirmRequest(Long recipientId) {}

    @GetMapping("/search")
    public List<Day7RecipientService.Candidate> search(
        @RequestParam(required=false) String name,
        @RequestParam(required=false) String phone) {
        if (name==null && phone==null)
            throw new org.springframework.web.server.ResponseStatusException(
                org.springframework.http.HttpStatus.BAD_REQUEST,"Recipient name or phone required");
        var byName=name==null ? null : service.resolve(AuthenticatedUser.id(),new ResolveRequest("NAME",name));
        var byPhone=phone==null ? null : service.resolve(AuthenticatedUser.id(),new ResolveRequest("PHONE",phone));
        if (byName==null) return byPhone;
        if (byPhone==null) return byName;
        // Exact conjunction, never pick a different user based on model preference.
        var phoneIds=byPhone.stream().map(Day7RecipientService.Candidate::recipientId).collect(java.util.stream.Collectors.toSet());
        return byName.stream().filter(c->phoneIds.contains(c.recipientId())).toList();
    }
    @PostMapping("/confirm")
    public Day7RecipientService.Confirmed confirm(@RequestBody ConfirmRequest body) {
        return service.confirm(AuthenticatedUser.id(),body);
    }
}
