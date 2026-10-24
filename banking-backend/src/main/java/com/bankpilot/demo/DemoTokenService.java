package com.bankpilot.demo;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Service;

/** LOCAL DEMO ONLY: random opaque tokens, hashed server-side, expire in 30 min. */
@Service
public class DemoTokenService {
    private static final Duration TTL = Duration.ofMinutes(30);
    private final Map<String, Session> sessions = new ConcurrentHashMap<>();
    private final SecureRandom random = new SecureRandom();
    private final Clock clock = Clock.systemUTC();

    record Session(BankPrincipal principal, Instant expiresAt) { }
    public record IssuedToken(String token, long expiresInSeconds) { }

    public IssuedToken issue(BankPrincipal principal) {
        byte[] raw = new byte[32];
        random.nextBytes(raw);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(raw);
        sessions.put(hash(token), new Session(principal, clock.instant().plus(TTL)));
        return new IssuedToken(token, TTL.getSeconds());
    }

    public Optional<BankPrincipal> resolve(String authorization) {
        if (authorization == null || !authorization.startsWith("Bearer ") || authorization.length() > 2048) {
            return Optional.empty();
        }
        String token = authorization.substring(7);
        if (!token.matches("[A-Za-z0-9_-]{43}")) return Optional.empty();
        Session session = sessions.get(hash(token));
        if (session == null) return Optional.empty();
        if (!session.expiresAt().isAfter(clock.instant())) {
            sessions.remove(hash(token));
            return Optional.empty();
        }
        return Optional.of(session.principal());
    }

    public void revoke(String authorization) {
        if (authorization != null && authorization.startsWith("Bearer ")) {
            sessions.remove(hash(authorization.substring(7)));
        }
    }

    private static String hash(String input) {
        try {
            byte[] bytes = MessageDigest.getInstance("SHA-256").digest(input.getBytes(StandardCharsets.UTF_8));
            return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        } catch (NoSuchAlgorithmException exc) {
            throw new IllegalStateException("SHA-256 unavailable", exc);
        }
    }
}
