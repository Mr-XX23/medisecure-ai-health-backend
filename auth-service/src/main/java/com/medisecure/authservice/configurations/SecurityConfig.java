package com.medisecure.authservice.configurations;

import com.medisecure.authservice.services.CookiesService;
import com.medisecure.authservice.services.JwtService;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
@EnableWebSecurity
@RequiredArgsConstructor
@ConditionalOnProperty(value = "security.enabled", havingValue = "true", matchIfMissing = true)
public class SecurityConfig {

    private final JwtService jwtService;
    private final JwtDecoder jwtDecoder;
    private final PublicEndpointsConfig publicEndpointsConfig;

    /**
     * Configure security filter chain
     * @param http HttpSecurity
     */
    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
                .csrf(csrf -> csrf.disable())
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(publicEndpointsConfig.getPublicEndpoints()).permitAll()
                        .anyRequest().authenticated()
                )
                .oauth2Login(oauth2 -> oauth2
                    .loginPage("/oauth2/authorization/google")
                    .defaultSuccessUrl("/api/v1/auth/oauth2/callback/google", true)
                )
                .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt -> jwt.decoder(jwtDecoder)))
                .addFilterBefore(new JwtAuthenticationFilter(jwtService, publicEndpointsConfig.getPublicEndpoints()),
                        UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
