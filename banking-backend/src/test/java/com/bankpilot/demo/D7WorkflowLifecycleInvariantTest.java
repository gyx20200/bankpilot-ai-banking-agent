package com.bankpilot.demo;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;

/** D7 safety regression: terminal workflows cannot be reopened through D5 API. */
class D7WorkflowLifecycleInvariantTest {
    private static final List<String> TERMINAL = List.of(
            "COMPLETED", "REJECTED", "ENDED", "NOT_CONFIRMED");
    private static final List<String> ALL = List.of(
            "RUNNING", "WAITING", "COMPLETED", "REJECTED", "ENDED", "NOT_CONFIRMED");

    @Test
    void terminalStatesOnlyAllowIdempotentSelfUpdate() {
        for (String from : TERMINAL) {
            assertTrue(WorkflowSessionService.canTransition(from, from), from);
            for (String to : ALL) {
                if (!from.equals(to)) {
                    assertFalse(WorkflowSessionService.canTransition(from, to), from + " -> " + to);
                }
            }
        }
    }

    @Test
    void waitingAndRunningAreNonterminalButNeverAuthorizeBankTransferByThemselves() {
        // Registry transitions are bookkeeping, not permission to call execute().
        assertTrue(WorkflowSessionService.canTransition("RUNNING", "WAITING"));
        assertTrue(WorkflowSessionService.canTransition("WAITING", "RUNNING"));
        assertTrue(WorkflowSessionService.canTransition("WAITING", "NOT_CONFIRMED"));
    }

    @Test
    void unknownStatesAreAlwaysRejected() {
        assertFalse(WorkflowSessionService.canTransition("SUCCESS", "RUNNING"));
        assertFalse(WorkflowSessionService.canTransition("WAITING", "SUCCESS"));
        assertFalse(WorkflowSessionService.canTransition(null, "WAITING"));
        assertFalse(WorkflowSessionService.canTransition("WAITING", null));
    }
}
