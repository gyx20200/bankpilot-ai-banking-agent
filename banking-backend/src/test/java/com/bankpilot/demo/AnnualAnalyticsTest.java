package com.bankpilot.demo;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;
import java.math.BigDecimal;
import java.time.LocalDateTime;
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
class AnnualAnalyticsTest {
    @Autowired JdbcTemplate jdbc;
    @BeforeEach void login() { asUser(1L); }
    @AfterEach void clear() { SecurityContextHolder.clearContext(); }
    private void asUser(long id) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(new BankPrincipal(id,"test"),null,List.of()));
    }
    private void tx(long account,String direction,String amount,String category,String time) {
        jdbc.update("INSERT INTO transactions(account_id,direction,amount,category,occurred_at) VALUES (?,?,?,?,?)",
            account,direction,new BigDecimal(amount),category,LocalDateTime.parse(time));
    }
    @Test void annualTotalsCategoriesAndBoundariesAreOwnerScoped() {
        tx(1,"IN","1000.00","工资","2020-01-01T00:00:00");
        tx(1,"OUT","35.10","餐饮","2020-01-31T23:59:59");
        tx(1,"OUT","10.20","餐饮","2020-12-31T23:59:59");
        tx(1,"OUT","1.00","购物","2020-12-01T00:00:00");
        tx(1,"OUT","900.00","购物","2021-01-01T00:00:00");
        tx(1,"OUT","900.00","购物","2019-12-31T23:59:59");
        tx(2,"OUT","999.00","购物","2020-04-01T00:00:00");
        var c=new AnnualAnalyticsController(jdbc);
        var r=c.annual("2020");
        assertThat(r.totalIncome()).isEqualByComparingTo("1000.00");
        assertThat(r.totalExpense()).isEqualByComparingTo("46.30");
        assertThat(r.netCashFlow()).isEqualByComparingTo("953.70");
        assertThat(r.monthlyBreakdown()).hasSize(12);
        assertThat(r.monthlyBreakdown().get(0).totalExpense()).isEqualByComparingTo("35.10");
        assertThat(r.monthlyBreakdown().get(1).totalExpense()).isEqualByComparingTo("0.00");
        assertThat(r.monthlyBreakdown().get(11).totalExpense()).isEqualByComparingTo("11.20");
        assertThat(r.categories()).anySatisfy(x->{
            assertThat(x.name()).isEqualTo("餐饮");assertThat(x.amount()).isEqualByComparingTo("45.30");assertThat(x.count()).isEqualTo(2);
        });
        assertThat(r.periodType()).isEqualTo("FULL_YEAR");
        asUser(2L);
        assertThat(c.annual("2020").totalExpense()).isEqualByComparingTo("999.00");
    }
    @Test void emptyYearReturnsZero() {
        var r=new AnnualAnalyticsController(jdbc).annual("1900");
        assertThat(r.totalIncome()).isEqualByComparingTo("0.00");
        assertThat(r.totalExpense()).isEqualByComparingTo("0.00");
        assertThat(r.categories()).isEmpty();
        assertThat(r.monthlyBreakdown()).hasSize(12);
    }
    @Test void currentYearIsNotProjectedIntoFuture() {
        LocalDateTime now=jdbc.queryForObject("SELECT CURRENT_TIMESTAMP",LocalDateTime.class);
        var r=new AnnualAnalyticsController(jdbc).annual(Integer.toString(now.getYear()));
        assertThat(r.periodType()).isEqualTo("YEAR_TO_DATE");
        assertThat(r.monthlyBreakdown()).hasSize(now.getMonthValue());
    }
    @Test void rejectsInvalidYearAndFutureYear() {
        var c=new AnnualAnalyticsController(jdbc);
        for(String y:List.of("0000","20","2026' OR 1=1","9999"))
            assertThat(assertThrows(ResponseStatusException.class,()->c.annual(y)).getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
    }
    @Test void requiresAuthentication() {
        clear();
        assertThat(assertThrows(ResponseStatusException.class,()->new AnnualAnalyticsController(jdbc).annual("2020")).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
    }
}
