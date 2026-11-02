package com.bankpilot.demo;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;
import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;

@JdbcTest
class MonthlyAnalyticsTest {
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void asDemoUser() {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(new BankPrincipal(1L, "张小明"), null, List.of()));
    }

    @AfterEach
    void clear() { SecurityContextHolder.clearContext(); }

    @Test
    void monthlyTotalsComeFromSqlAndDoNotLeakOtherUserData() {
        MonthlyAnalyticsController.MonthlyReport result = new MonthlyAnalyticsController(jdbc).monthly("2026-10");
        assertThat(result.month()).isEqualTo("2026-10");
        assertThat(result.totalIncome()).isEqualByComparingTo(new BigDecimal("8000.00"));
        assertThat(result.totalExpense()).isEqualByComparingTo(new BigDecimal("60.00"));
        assertThat(result.netCashFlow()).isEqualByComparingTo(new BigDecimal("7940.00"));
        assertThat(result.categories()).hasSize(2);
        assertThat(result.categories().stream().map(MonthlyAnalyticsController.CategoryTotal::name).toList())
            .containsExactlyInAnyOrder("餐饮", "订阅").doesNotContain("购物");
        assertThat(result.source()).isEqualTo("mysql");
    }

    @Test
    void emptyMonthIsZeroNotInvented() {
        var result = new MonthlyAnalyticsController(jdbc).monthly("2026-09");
        assertThat(result.totalExpense()).isEqualByComparingTo(BigDecimal.ZERO);
        assertThat(result.categories()).isEmpty();
    }

    @Test
    void invalidMonthCannotChangeSqlOrCauseModelQueryInjection() {
        var controller = new MonthlyAnalyticsController(jdbc);
        for (String invalid : List.of("2026-13", "2026-1", "2026-10' OR 1=1 --", "yesterday")) {
            ResponseStatusException exc = assertThrows(ResponseStatusException.class, () -> controller.monthly(invalid));
            assertThat(exc.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        }
    }
}
