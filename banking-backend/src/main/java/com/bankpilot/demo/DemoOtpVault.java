package com.bankpilot.demo;

import java.security.SecureRandom;
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

/**
 * Development-only fake delivery channel. Disabled by default.
 * This is NOT a second factor: it is visible to the same logged-in browser.
 * Replace this whole component with an actual independent OTP provider in production.
 */
@Service
public class DemoOtpVault {
    private final boolean enabled;
    private final Map<Long, Entry> codes = new ConcurrentHashMap<>();
    private final SecureRandom random = new SecureRandom();
    private record Entry(long userId, String code, Instant expiresAt) { }

    public DemoOtpVault(@Value("${bankpilot.demo.otp.debug-enabled:false}") boolean enabled) {
        this.enabled = enabled;
    }

    public String generate() { return "%06d".formatted(random.nextInt(1_000_000)); }

    public void store(long orderId, long userId, String code, Instant expiry) {
        if (enabled) codes.put(orderId, new Entry(userId, code, expiry));
    }

    public void clear(long orderId) { codes.remove(orderId); }

    public String getDebugCode(long orderId, long userId) {
        if (!enabled) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Debug OTP disabled");
        Entry entry = codes.get(orderId);
        if (entry == null || entry.userId() != userId || !entry.expiresAt().isAfter(Instant.now())) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Debug OTP unavailable");
        }
        return entry.code();
    }
}
