package com.bankpilot.demo;

import static org.junit.jupiter.api.Assertions.*;
import java.time.OffsetDateTime;
import org.junit.jupiter.api.Test;

/** DTO contract checks matched to agent-service/app/banking_client.py. */
class Day7AgentContractTest {
  @Test void authUsesFullNameAndReturnsTopLevelFields(){
    var r=new Day7AuthController.RegisterRequest("zhangsan","张三","test-secure-password","13800138001");
    assertEquals("张三",r.fullName());
    assertEquals("REGISTERED",new Day7AuthService.Registration("REGISTERED",3).status());
    assertEquals("Bearer",new Day7AuthService.LoginResult("token","Bearer",1800,"张三").tokenType());
  }
  @Test void recipientUsesRegisteredIdentityNotPayeeId(){
    assertEquals(3L,new Day7RecipientController.ConfirmRequest(3L).recipientId());
    var c=new Day7RecipientService.Candidate(3L,"张三","****1234");
    assertEquals(3,c.recipientId());
    assertEquals("****1234",c.accountMasked());
  }
  @Test void aaDraftAndScheduleRequestMatchPythonDto(){
    var aa=new Day7AaController.Prepare(java.util.List.of("张三","李四"),"300.00","total_with_self","聚餐","aa-unique-001");
    assertEquals("total_with_self",aa.splitMode());
    var s=new Day7ScheduledController.CreateRequest(7L,"10.00","2026-11-01T15:00:00+08:00","生活费","sched-unique-001");
    assertEquals(8*60,OffsetDateTime.parse(s.executeAt()).getOffset().getTotalSeconds()/60);
    assertEquals("246810",new Day7ScheduledController.AuthorizeRequest("request-0001",true,"246810").otpCode());
  }
}
