package com.bankpilot.demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/** One JVM demo scheduler. Coordinator owns transactional row locking. */
@Component
public class Day7ScheduledRunner {
    private final JdbcTemplate jdbc;
    private final Day7ScheduledExecutionCoordinator coordinator;
    public Day7ScheduledRunner(JdbcTemplate jdbc,Day7ScheduledExecutionCoordinator coordinator){
        this.jdbc=jdbc;this.coordinator=coordinator;
    }
    @Scheduled(fixedDelayString="${bankpilot.day7.scheduler-ms:5000}")
    public void tick(){
        var due=jdbc.query("""
          SELECT id FROM scheduled_transfers
          WHERE status='SCHEDULED' AND scheduled_at_utc <= UTC_TIMESTAMP(6)
          ORDER BY scheduled_at_utc,id LIMIT 20
          """,(rs,n)->rs.getLong(1));
        for(long id:due){
            try{coordinator.execute(id);}catch(Exception ex){
                // Do not auto-retry unknown cash outcomes without reconciliation.
                // A transaction rollback leaves SCHEDULED for inspection.
                coordinator.markUnknown(id);
                System.err.println("SCHEDULE_EXECUTION_UNKNOWN id="+id+" exception="+ex.getClass().getSimpleName());
            }
        }
    }
}
