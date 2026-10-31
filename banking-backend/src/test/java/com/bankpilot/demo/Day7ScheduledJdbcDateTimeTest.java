package com.bankpilot.demo;

import java.sql.Timestamp;
import java.time.LocalDateTime;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class Day7ScheduledJdbcDateTimeTest {
    @Test
    void mysqlLocalDateTimeAndJdbcTimestampAreBothSupported() {
        LocalDateTime expected = LocalDateTime.of(2026, 11, 1, 15, 0, 0);
        assertEquals(expected, Day7ScheduledService.dbDateTime(expected));
        assertEquals(expected, Day7ScheduledService.dbDateTime(Timestamp.valueOf(expected)));
    }

    @Test
    void unsupportedDateTypesFailExplicitly() {
        assertThrows(IllegalStateException.class, () -> Day7ScheduledService.dbDateTime(null));
        assertThrows(IllegalStateException.class, () -> Day7ScheduledService.dbDateTime("2026-11-01"));
    }
}
