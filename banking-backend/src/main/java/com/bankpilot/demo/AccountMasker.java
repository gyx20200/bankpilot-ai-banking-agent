package com.bankpilot.demo;

/** Returns only a fixed masked suffix, never the full account identifier. */
final class AccountMasker {
    private AccountMasker() { }

    static String mask(String accountNumber) {
        if (accountNumber == null || accountNumber.isBlank()) return "****";
        return "****" + accountNumber.substring(Math.max(0, accountNumber.length() - 4));
    }
}
