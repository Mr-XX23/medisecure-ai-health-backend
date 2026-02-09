package com.medisecure.authservice.configurations;

import com.medisecure.authservice.dto.CookieUtil;
import com.medisecure.authservice.services.JwtService;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.UnavailableException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.Arrays;
import java.util.Collections;

@Slf4j
@RequiredArgsConstructor
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    private final JwtService jwtService;
    private final String[] publicEndpoints;

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain) throws ServletException, IOException {
        String requestPath = request.getRequestURI();
        log.debug("I am here in JWT Filter for path: {}", requestPath);

        // Skip JWT validation for public endpoints
        if (Arrays.stream(publicEndpoints).anyMatch(requestPath::startsWith)) {
            filterChain.doFilter(request, response);
            return;
        }

        String accessToken = CookieUtil.getCookieValue(request, "access_token").orElse(null);
        log.info(accessToken);
        if (accessToken != null) {
            try {
                log.info("Attempting to authenticate using JWT Token");
                Jwt jwt = jwtService.validateAndDecodeToken(accessToken);
                String username = jwt.getSubject();

                UsernamePasswordAuthenticationToken authentication =
                        new UsernamePasswordAuthenticationToken(username, null, Collections.emptyList());
                authentication.setDetails(new WebAuthenticationDetailsSource().buildDetails(request));

                SecurityContextHolder.getContext().setAuthentication(authentication);
            } catch (Exception e) {
                log.error("Cannot set user authentication: {}", e.getMessage());
            }
        }
        filterChain.doFilter(request, response);
    }
}
