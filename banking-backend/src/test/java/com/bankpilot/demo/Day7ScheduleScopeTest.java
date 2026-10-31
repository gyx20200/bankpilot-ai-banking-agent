package com.bankpilot.demo;

import org.junit.jupiter.api.Test;
import java.math.BigDecimal;
import java.time.Instant;
import static org.junit.jupiter.api.Assertions.*;

class Day7ScheduleScopeTest {
    @Test void scopeIncludesExactRecipientAmountAndTime() {
        var due=Instant.parse("2026-11-02T07:00:00Z");
        var base=Day7ScheduledService.scope(1,10,20,new BigDecimal("200.00"),due,"lunch");
        assertEquals(64,base.length());
        assertEquals(base,Day7ScheduledService.scope(1,10,20,new BigDecimal("200.00"),due,"lunch"));
        assertNotEquals(base,Day7ScheduledService.scope(1,10,21,new BigDecimal("200.00"),due,"lunch"));
        assertNotEquals(base,Day7ScheduledService.scope(1,10,20,new BigDecimal("200.01"),due,"lunch"));
        assertNotEquals(base,Day7ScheduledService.scope(1,10,20,new BigDecimal("200.00"),due.plusSeconds(60),"lunch"));
    }
}
