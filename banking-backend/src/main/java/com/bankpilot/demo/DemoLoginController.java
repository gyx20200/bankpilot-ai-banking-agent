package com.bankpilot.demo;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import jakarta.servlet.http.HttpServletRequest;

/** LOCAL DEMO credential based login; replace with real identity provider after contest. */
@RestController
@RequestMapping("/api/auth")
public class DemoLoginController {
    private final DemoTokenService tokenService;
    private final String demoPassword;
    private final Map<String, FailureBucket> failures = new ConcurrentHashMap<>();

    private record FailureBucket(int attempts, Instant windowStart, Instant blockedUntil) { }
    public record LoginRequest(String username, String password) { }
    public record LoginResponse(String token, String tokenType, long expiresInSeconds, String displayName) { }

    public DemoLoginController(DemoTokenService tokenService, @Value("${bankpilot.demo.login.password:}") String demoPassword) {
        this.tokenService = tokenService;
        this.demoPassword = demoPassword;
    }

    @PostMapping("/demo-login")
    public LoginResponse demoLogin(@RequestBody LoginRequest body, HttpServletRequest request) {
        if (demoPassword.length() < 12) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                    "DEMO_LOGIN_PASSWORD must be set to at least 12 characters");
        }
        String client = request.getRemoteAddr(); // localhost-only demo: no proxy trust.
        FailureBucket bucket = failures.get(client);
        if (bucket != null && bucket.blockedUntil().isAfter(Instant.now())) {
            throw new ResponseStatusException(HttpStatus.TOO_MANY_REQUESTS, "Too many failed logins; retry later");
        }
        boolean valid = body != null && "demo".equals(body.username()) && body.password() != null &&
            MessageDigest.isEqual(body.password().getBytes(StandardCharsets.UTF_8), demoPassword.getBytes(StandardCharsets.UTF_8));
        if (!valid) {
            failures.compute(client, (k, old) -> {
                Instant now = Instant.now();
                int attempts = old == null || old.windowStart().plus(Duration.ofSeconds(60)).isBefore(now)
                        ? 1 : old.attempts() + 1;
                Instant start = attempts == 1 ? now : old.windowStart();
                return new FailureBucket(attempts, start,
                    attempts >= 5 ? now.plus(Duration.ofSeconds(60)) : Instant.EPOCH);
            });
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Invalid demo credentials");
        }
        failures.remove(client);
        DemoTokenService.IssuedToken token = tokenService.issue(new BankPrincipal(1L, "张小明"));
        return new LoginResponse(token.token(), "Bearer", token.expiresInSeconds(), "张小明");
    }

    @PostMapping("/logout")
    public Map<String, String> logout(@RequestHeader(value = "Authorization", required = false) String authorization) {
        tokenService.revoke(authorization);
        return Map.of("status", "logged_out");
    }
}
