package com.bankpilot.demo;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/** Demo-only registered-user endpoints. Authentication remains in existing DemoTokenService. */
@RestController
@RequestMapping("/api/auth")
public class Day7AuthController {
    private final Day7AuthService service;

    public Day7AuthController(Day7AuthService service) { this.service = service; }

    public record RegisterRequest(String username, String fullName, String password, String phone) {}
    public record LoginRequest(String username, String password) {}

    @PostMapping("/register")
    @ResponseStatus(HttpStatus.CREATED)
    public Day7AuthService.Registration register(@RequestBody RegisterRequest request) {
        return service.register(request);
    }

    @PostMapping("/login")
    public Day7AuthService.LoginResult login(@RequestBody LoginRequest request, HttpServletRequest servletRequest) {
        return service.login(request, servletRequest.getRemoteAddr());
    }

    @GetMapping("/me")
    public Day7AuthService.Profile me() {
        return service.profile(AuthenticatedUser.id());
    }
}
