
package com.bankpilot.demo;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            DemoTokenService tokens
    ) throws Exception {

        http
            .csrf(csrf -> csrf.disable())

            .sessionManagement(session ->
                session.sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS
                )
            )

            .formLogin(form -> form.disable())
            .httpBasic(basic -> basic.disable())
            .logout(logout -> logout.disable())

            .authorizeHttpRequests(auth -> auth

                // Allow Spring Boot to process errors normally.
                .dispatcherTypeMatchers(
                    DispatcherType.ERROR
                ).permitAll()

                // Public endpoints.
                .requestMatchers(
                    "/api/demo/health",
                    "/api/auth/demo-login"
                ).permitAll()

                // All business endpoints require authentication.
                .anyRequest().authenticated()
            )

            .exceptionHandling(ex ->
                ex.authenticationEntryPoint(
                    (request, response, exception) -> {
                        response.setStatus(
                            HttpServletResponse.SC_UNAUTHORIZED
                        );

                        response.setContentType(
                            MediaType.APPLICATION_JSON_VALUE
                        );

                        response.getWriter().write(
                            "{\"error\":\"UNAUTHORIZED\","
                            + "\"message\":\"Please log in\"}"
                        );
                    }
                )
            )

            .addFilterBefore(
                new BearerTokenFilter(tokens),
                UsernamePasswordAuthenticationFilter.class
            );

        return http.build();
    }
}
