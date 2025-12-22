package com.medisecure.authservice.services;

import com.medisecure.authservice.models.AuthSecurityEvent;
import com.medisecure.authservice.models.AuthUserCredentials;
import com.medisecure.authservice.repository.AuthSecurityEventRepository;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;

@Slf4j
@Service
@RequiredArgsConstructor
public class AuthSecurityEventService {

    private final AuthSecurityEventRepository securityEvents;

    @Async("securityEventExecutor")
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void logSecurityEvent(AuthUserCredentials user, String eventType,
                              String eventData, HttpServletRequest httprequest) {

        AuthSecurityEvent loginEvent = AuthSecurityEvent.builder()
                .authUser(user)
                .eventType(eventType)
                .eventData(eventData)
                .eventTime(LocalDateTime.now())
                .ipAddress(getIpAddress(httprequest))
                .userAgent(getUserAgent(httprequest))
                .build();

        try {
            AuthSecurityEvent savedEvent = securityEvents.save(loginEvent);
            log.info("Saved login event with id: {}", savedEvent.getEventId());
        } catch (Exception e) {
            log.error("Failed to save security event: {}", e.getMessage());
        }
    }

    public static String getIpAddress(HttpServletRequest request) {
        if (request == null) return "UNKNOWN";

        String ip = request.getHeader("X-Forwarded-For");
        if (ip == null || ip.isEmpty() || "unknown".equalsIgnoreCase(ip)) {
            ip = request.getHeader("X-Real-IP");
        }
        if (ip == null || ip.isEmpty() || "unknown".equalsIgnoreCase(ip)) {
            ip = request.getRemoteAddr();
        }
        return ip != null ? ip.split(",")[0].trim() : "UNKNOWN";
    }

    public static String getUserAgent(HttpServletRequest request) {
        if (request == null) return "UNKNOWN";
        String userAgent = request.getHeader("User-Agent");
        return userAgent != null ? userAgent : "UNKNOWN";
    }
}
