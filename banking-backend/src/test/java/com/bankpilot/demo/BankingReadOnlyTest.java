package com.bankpilot.demo;

import static org.assertj.core.api.Assertions.assertThat;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.test.context.TestPropertySource;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * Offline H2 test data: covers SQL mappings and demo-user isolation.
 * MySQL + Java + Python acceptance is separately tested by tests/day2_smoke_test.py.
 */
@JdbcTest
@TestPropertySource(properties = "spring.datasource.url=jdbc:h2:mem:bankpilotday3readonly;DB_CLOSE_DELAY=-1")
class BankingReadOnlyTest {
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void authenticatedDemoUser() {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(new BankPrincipal(1L, "张小明"), null, List.of()));
    }

    @AfterEach
    void clearAuthentication() { SecurityContextHolder.clearContext(); }

    @Test
    void balanceIsLoadedFromDatabaseAndMasked() {
        var view = new BalanceController(jdbc).balance();
        assertThat(view.userName()).isEqualTo("张小明");
        assertThat(view.accountNoMasked()).isEqualTo("****6688");
        assertThat(view.balance()).isEqualByComparingTo(new BigDecimal("12580.50"));
        assertThat(view.source()).isEqualTo("mysql");
    }

    @Test
    void transactionsAreLimitedToCurrentDemoUserAndOrderedByTime() {
        var items = new TransactionController(jdbc).listTransactions();
        assertThat(items).hasSize(3);
        assertThat(items.get(0).merchantName()).isEqualTo("视频会员");
        assertThat(items.get(0).occurredAt()).isEqualTo("2026-10-08 08:00:00");
        assertThat(items.get(1).amount()).isEqualByComparingTo(new BigDecimal("35.00"));
        assertThat(items.stream().map(TransactionController.TransactionView::merchantName).toList()).doesNotContain("其他用户商户");
    }

    @Test
    void payeesContainOnlyOwnedRecordsAndMaskedAccounts() {
        var items = new PayeeController(jdbc).listPayees();
        assertThat(items).hasSize(1);
        assertThat(items.get(0).payeeName()).isEqualTo("李四");
        assertThat(items.get(0).payeeAccountMasked()).isEqualTo("****5291");
        assertThat(items.get(0).payeeAccountMasked()).doesNotContain("DEMO");
    }

    @Test
    void subscriptionsAreScopedAndDateFormatted() {
        var items = new SubscriptionController(jdbc).listSubscriptions();
        assertThat(items).hasSize(2);
        assertThat(items.get(0).merchantName()).isEqualTo("视频会员");
        assertThat(items.get(0).billingCycle()).isEqualTo("MONTHLY");
        assertThat(items.get(0).nextPayDate()).isEqualTo("2026-11-08");
        assertThat(items.stream().map(SubscriptionController.SubscriptionView::merchantName).toList()).doesNotContain("其他用户会员");
    }

    @Test
    void maskerNeverReturnsWholeAccountNumber() {
        assertThat(AccountMasker.mask("DEMO-5291")).isEqualTo("****5291");
        assertThat(AccountMasker.mask(null)).isEqualTo("****");
    }
}
