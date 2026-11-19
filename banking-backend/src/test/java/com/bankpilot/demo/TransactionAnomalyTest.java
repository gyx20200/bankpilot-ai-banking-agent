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
class TransactionAnomalyTest {
    @Autowired JdbcTemplate jdbc;
    @BeforeEach void login() {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(new BankPrincipal(1L,"test"),null,List.of()));
    }
    @AfterEach void clear() { SecurityContextHolder.clearContext(); }
    private void tx(long account,String direction,String amount,String merchant,String time) {
        jdbc.update("INSERT INTO transactions(account_id,direction,amount,category,merchant_name,occurred_at) VALUES (?,?,?,?,?,?)",
            account,direction,new BigDecimal(amount),"购物",merchant,LocalDateTime.parse(time));
    }
    @Test void sqlScopesToOwnerAndMonthAndOnlyOutflows() {
        tx(1,"OUT","1000.00","A","2020-10-01T09:00:00");
        tx(1,"OUT","999.99","B","2020-10-01T09:01:00");
        tx(1,"OUT","25.00","C","2020-10-01T10:00:00");
        tx(1,"OUT","25.00","C","2020-10-01T10:10:00");
        tx(1,"OUT","25.00","C","2020-10-01T10:20:01");
        tx(1,"OUT","25.00","D","2020-10-01T10:21:00");
        tx(1,"IN","5000.00","C","2020-10-01T10:21:00");
        tx(2,"OUT","5000.00","C","2020-10-01T10:21:00");
        tx(1,"OUT","5000.00","E","2020-11-01T00:00:00");
        var r=new TransactionAnomalyController(jdbc).anomalies("2020-10");
        assertThat(r.scannedCount()).isEqualTo(6);
        assertThat(r.anomalyCount()).isEqualTo(2);
        assertThat(r.items()).extracting(TransactionAnomalyController.Event::ruleCode)
            .containsExactly("LARGE_OUTFLOW","POSSIBLE_DUPLICATE");
        assertThat(r.items().get(1).relatedTransactionId()).isNotNull();
    }
    @Test void equalAmountDifferentAccountOrBlankMerchantDoesNotMatch() {
        LocalDateTime t=LocalDateTime.parse("2020-10-01T10:00:00");
        var rows=List.of(
          new TransactionAnomalyController.Tx(1,1,new BigDecimal("25.0"),"购物","C",t),
          new TransactionAnomalyController.Tx(2,2,new BigDecimal("25.00"),"购物","C",t.plusMinutes(1)),
          new TransactionAnomalyController.Tx(3,1,new BigDecimal("25.00"),"购物",null,t.plusMinutes(2)),
          new TransactionAnomalyController.Tx(4,1,new BigDecimal("25.00"),"购物"," ",t.plusMinutes(3)),
          new TransactionAnomalyController.Tx(5,1,new BigDecimal("25.00"),"购物","c ",t.plusMinutes(4)));
        var events=TransactionAnomalyController.detect(rows);
        assertThat(events).hasSize(1);
        assertThat(events.get(0).transactionId()).isEqualTo(5);
        assertThat(events.get(0).relatedTransactionId()).isEqualTo(1L);
    }
    @Test void oneTransactionCanMatchTwoRules() {
        LocalDateTime t=LocalDateTime.parse("2020-10-01T10:00:00");
        var rows=List.of(
            new TransactionAnomalyController.Tx(1,1,new BigDecimal("1000"),"购物","C",t),
            new TransactionAnomalyController.Tx(2,1,new BigDecimal("1000.00"),"购物","C",t.plusMinutes(1)));
        assertThat(TransactionAnomalyController.detect(rows)).hasSize(3);
    }
    @Test void emptyMonthAndBadInput() {
        var c=new TransactionAnomalyController(jdbc);
        assertThat(c.anomalies("1900-01").items()).isEmpty();
        for(String m:List.of("2026-13","2026-1","0000-01","9999-01"))
            assertThat(assertThrows(ResponseStatusException.class,()->c.anomalies(m)).getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
    }
    @Test void requiresAuthentication() {
        clear();
        assertThat(assertThrows(ResponseStatusException.class,()->new TransactionAnomalyController(jdbc).anomalies("2020-10")).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
    }
}
