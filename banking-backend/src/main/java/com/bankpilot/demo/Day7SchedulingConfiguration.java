package com.bankpilot.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;

@Configuration
@EnableScheduling
@ConditionalOnProperty(name="bankpilot.day7.jobs.enabled",havingValue="true")
public class Day7SchedulingConfiguration {}
