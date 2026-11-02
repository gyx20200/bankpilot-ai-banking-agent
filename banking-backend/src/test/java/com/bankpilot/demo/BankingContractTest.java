package com.bankpilot.demo;
import static org.junit.jupiter.api.Assertions.*;
import java.time.Instant;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
class BankingContractTest {
  @Test void scheduleScopeIsBoundToEveryCriticalField(){
    var when=Instant.parse("2026-12-01T02:00:00Z");
    var a=Day7ScheduledService.scope(1,1,2,new BigDecimal("100.00"),when,"meal");
    assertEquals(a,Day7ScheduledService.scope(1,1,2,new BigDecimal("100.00"),when,"meal"));
    assertNotEquals(a,Day7ScheduledService.scope(1,1,3,new BigDecimal("100.00"),when,"meal"));
    assertNotEquals(a,Day7ScheduledService.scope(1,1,2,new BigDecimal("101.00"),when,"meal"));
    assertNotEquals(a,Day7ScheduledService.scope(2,1,2,new BigDecimal("100.00"),when,"meal"));
  }
  @Test void transferPrepareCarriesRemark(){
    var x=new TransferPrepareController.PrepareRequest(7L,"13.00","day7-test-key", "AA 餐费");
    assertEquals("AA 餐费",x.remark());
  }
}
