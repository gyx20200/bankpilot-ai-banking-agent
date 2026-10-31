package com.bankpilot.demo;

import org.springframework.web.bind.annotation.*;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/scheduled-transfers")
public class Day7ScheduledController {
    private final Day7ScheduledService service;
    public Day7ScheduledController(Day7ScheduledService service){this.service=service;}
    public record CreateRequest(Long payeeId,String amount,String executeAt,String remark,String requestId){}
    public record AuthorizeRequest(String requestId,Boolean confirmed,String otpCode){}
    public record RequestId(String requestId){}

    @PostMapping("/prepare")
    public Map<String,Object> create(@RequestBody CreateRequest body){return service.create(AuthenticatedUser.id(),body);}
    @PostMapping("/{id}/authorize")
    public Map<String,Object> authorize(@PathVariable long id,@RequestBody AuthorizeRequest body){
        return service.authorize(AuthenticatedUser.id(),id,body);
    }
    @PostMapping("/{id}/otp/request")
    public Map<String,Object> otp(@PathVariable long id){return service.requestOtp(AuthenticatedUser.id(),id);}
    @GetMapping("/{id}/demo-otp")
    public Map<String,String> debug(@PathVariable long id,jakarta.servlet.http.HttpServletRequest request){
        return service.debugOtp(AuthenticatedUser.id(),id,request);
    }
    @PostMapping("/{id}/cancel")
    public Map<String,Object> cancel(@PathVariable long id,@RequestBody RequestId body){
        return service.cancel(AuthenticatedUser.id(),id,body);
    }
    @GetMapping("/mine")
    public List<Map<String,Object>> mine(){return service.list(AuthenticatedUser.id());}
    @GetMapping("/{id}")
    public Map<String,Object> get(@PathVariable long id){return service.get(AuthenticatedUser.id(),id);}
}
