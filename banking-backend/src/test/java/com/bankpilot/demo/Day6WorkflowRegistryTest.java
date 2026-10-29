package com.bankpilot.demo;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@Sql(scripts={"/day6-test-schema.sql","/day6-workflow-test-schema.sql"},
     executionPhase=Sql.ExecutionPhase.BEFORE_TEST_CLASS)
class Day6WorkflowRegistryTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach void reset() {
        jdbc.update("DELETE FROM agent_workflow_tasks");
        jdbc.update("DELETE FROM agent_workflow_runs");
        jdbc.update("DELETE FROM subscription_cancel_events");
        jdbc.update("DELETE FROM subscription_cancel_orders");
        jdbc.update("UPDATE subscriptions SET status='ACTIVE',cancelled_at=NULL WHERE id=1");
    }
    private String auth() throws Exception {
        String login = mvc.perform(post("/api/auth/demo-login")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"username\":\"demo\",\"password\":\"JUnitDemoPassword2026!\"}"))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        return "Bearer " + mapper.readTree(login).get("token").asText();
    }
    private JsonNode register(String auth, String workflowId, List<Map<String,String>> tasks) throws Exception {
        String json = mapper.writeValueAsString(Map.of("workflowId",workflowId,"tasks",tasks));
        String out = mvc.perform(post("/api/agent/workflow-runs")
            .header("Authorization",auth).contentType(MediaType.APPLICATION_JSON).content(json))
            .andExpect(status().isCreated()).andReturn().getResponse().getContentAsString();
        return mapper.readTree(out);
    }
    private Map<String,String> a(String month) {return Map.of("type","monthly_analytics","month",month);}
    private Map<String,String> b() {return Map.of("type","list_subscriptions");}
    private Map<String,String> c() {return Map.of("type","cancel_subscription","merchantName","视频会员");}

    @Test void allSevenCombinationsAndDependencies() throws Exception {
        String token=auth();
        var combinations=List.of(List.of(a("2026-09")),List.of(b()),List.of(c()),
            List.of(a("2026-09"),b()),List.of(a("2026-10"),c()),
            List.of(b(),c()),List.of(a("2026-10"),b(),c()));
        int i=0;
        for (var tasks: combinations) {
            String id="wf-seven-" + (++i) + "-xyz";
            JsonNode snapshot=register(token,id,tasks);
            assertThat(snapshot.get("tasks").size()).isEqualTo(tasks.size());
            assertThat(snapshot.get("workflowId").asText()).isEqualTo(id);
            assertThat(snapshot.get("cancellationOrders").size()).isEqualTo(0);
            if (tasks.stream().anyMatch(t -> "cancel_subscription".equals(t.get("type")))) {
                JsonNode dependency=snapshot.get("tasks").get(tasks.size()-1).get("dependsOn");
                assertThat(dependency.toString()).contains("human_approval");
                if (tasks.stream().anyMatch(t -> "list_subscriptions".equals(t.get("type"))))
                    assertThat(dependency.toString()).contains("list_subscriptions");
                else assertThat(dependency.toString()).contains("internal_subscription_lookup");
            }
        }
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM agent_workflow_runs",Integer.class)).isEqualTo(7);
        // The registry is entirely side-effect free.
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM subscription_cancel_orders",Integer.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT status FROM subscriptions WHERE id=1",String.class)).isEqualTo("ACTIVE");
    }

    @Test void idempotencyAndConflict() throws Exception {
        String token=auth(), id="wf-unique-key-0001";
        var first=register(token,id,List.of(a("2026-09"),b()));
        var again=register(token,id,List.of(b(),a("2026-09")));
        assertThat(first.get("tasks")).isEqualTo(again.get("tasks"));
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM agent_workflow_runs",Integer.class)).isEqualTo(1);
        mvc.perform(post("/api/agent/workflow-runs").header("Authorization",token)
            .contentType(MediaType.APPLICATION_JSON)
            .content(mapper.writeValueAsString(Map.of("workflowId",id,"tasks",List.of(a("2026-10"),b())))))
            .andExpect(status().isConflict());
    }

    @Test void invalidPlansDoNotWriteAndUnauthorizedRejected() throws Exception {
        String token=auth();
        mvc.perform(post("/api/agent/workflow-runs").contentType(MediaType.APPLICATION_JSON)
            .content("{\"workflowId\":\"wf-anon-0001\",\"tasks\":[{\"type\":\"list_subscriptions\"}]}"))
            .andExpect(status().isUnauthorized());
        for (String json : List.of(
            "{\"workflowId\":\"wf-invalid-month\",\"tasks\":[{\"type\":\"monthly_analytics\",\"month\":\"2026-13\"}]}",
            "{\"workflowId\":\"wf-unknown-type\",\"tasks\":[{\"type\":\"execute_transfer\"}]}",
            "{\"workflowId\":\"wf-duplicated\",\"tasks\":[{\"type\":\"list_subscriptions\"},{\"type\":\"list_subscriptions\"}]}",
            "{\"workflowId\":\"wf-no-merchant\",\"tasks\":[{\"type\":\"cancel_subscription\"}]}",
            "{\"workflowId\":\"wf-empty-tasks\",\"tasks\":[]}") ) {
            mvc.perform(post("/api/agent/workflow-runs").header("Authorization",token)
                .contentType(MediaType.APPLICATION_JSON).content(json))
                .andExpect(status().isBadRequest());
        }
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM agent_workflow_runs",Integer.class)).isZero();
    }

    @Test void snapshotReconcilesRealCancellationOrder() throws Exception {
        String token=auth(), wf="wf-recovery-000001";
        register(token,wf,List.of(a("2026-09"),c()));
        String prep=mapper.writeValueAsString(Map.of("subscriptionId",1,"requestId","cancel-req-00001","workflowId",wf));
        String resp=mvc.perform(post("/api/subscription-cancellations/prepare")
            .header("Authorization",token).contentType(MediaType.APPLICATION_JSON).content(prep))
            .andExpect(status().isCreated()).andReturn().getResponse().getContentAsString();
        long id=mapper.readTree(resp).get("orderId").asLong();
        mvc.perform(get("/api/agent/workflow-runs/"+wf).header("Authorization",token))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.businessPhase").value("WAITING_USER_APPROVAL"))
            .andExpect(jsonPath("$.cancellationOrders[0].orderId").value(id));
        mvc.perform(post("/api/subscription-cancellations/"+id+"/authorize")
            .header("Authorization",token).contentType(MediaType.APPLICATION_JSON)
            .content("{\"confirmed\":true}"))
            .andExpect(status().isOk());
        mvc.perform(get("/api/agent/workflow-runs/"+wf).header("Authorization",token))
            .andExpect(jsonPath("$.businessPhase").value("AUTHORIZED_NOT_EXECUTED"));
        mvc.perform(post("/api/subscription-cancellations/"+id+"/execute")
            .header("Authorization",token)).andExpect(status().isOk());
        mvc.perform(get("/api/agent/workflow-runs/"+wf).header("Authorization",token))
            .andExpect(jsonPath("$.businessPhase").value("BANK_CANCEL_SUCCESS"));
    }


    @Test void cannotMistakeWrongMerchantForPlannedCancellation() throws Exception {
        String token=auth(), wf="wf-wrong-merchant-01";
        register(token,wf,List.of(c())); // Plan: cancel video membership.
        String prep=mapper.writeValueAsString(Map.of("subscriptionId",2,"requestId","cancel-wrong-001","workflowId",wf));
        mvc.perform(post("/api/subscription-cancellations/prepare")
            .header("Authorization",token).contentType(MediaType.APPLICATION_JSON).content(prep))
            .andExpect(status().isCreated());
        mvc.perform(get("/api/agent/workflow-runs/"+wf).header("Authorization",token))
            .andExpect(jsonPath("$.businessPhase").value("ORDER_TARGET_MISMATCH_REQUIRES_REVIEW"));
        assertThat(jdbc.queryForObject("SELECT status FROM subscriptions WHERE id=1", String.class))
            .isEqualTo("ACTIVE");
    }

    @Test void workflowOwnershipEnforced() throws Exception {
        String token=auth();
        register(token,"wf-owner-00001",List.of(a("2026-08")));
        mvc.perform(get("/api/agent/workflow-runs/wf-not-found-02").header("Authorization",token))
            .andExpect(status().isNotFound());
        mvc.perform(get("/api/agent/workflow-runs/wf-owner-00001"))
            .andExpect(status().isUnauthorized());
    }
}
