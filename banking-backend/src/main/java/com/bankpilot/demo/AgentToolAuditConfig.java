package com.bankpilot.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class AgentToolAuditConfig implements WebMvcConfigurer {
    private final JdbcTemplate jdbc;
    public AgentToolAuditConfig(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new AgentToolAuditInterceptor(jdbc))
            .addPathPatterns(
                "/api/demo/balance", "/api/demo/transactions",
                "/api/demo/payees", "/api/demo/subscriptions",
                "/api/transfers/prepare", "/api/demo/analytics/monthly"
            );
    }
}
