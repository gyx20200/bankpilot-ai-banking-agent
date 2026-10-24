package com.bankpilot.demo;

/** Account owner identity from server validated bearer token, never model input. */
public record BankPrincipal(long userId, String displayName) { }
