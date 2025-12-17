package com.medisecure.authservice.services;

import com.medisecure.authservice.dto.loginregistration.LoginResponse;
import com.medisecure.authservice.exceptions.BadRequestException;
import com.medisecure.authservice.exceptions.ForbiddenException;
import com.medisecure.authservice.models.AuthSecurityEvent;
import com.medisecure.authservice.repository.AuthSecurityEventRepository;
import com.medisecure.authservice.repository.UserRepository;
import com.medisecure.authservice.models.AuthUserCredentials;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.constraints.NotBlank;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.Set;

@Service
@RequiredArgsConstructor
@Slf4j
public class UserLoginService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final AuthSecurityEventRepository securityEvents;

    private final JwtService jwtService;
    private final TokenService tokenService;
    private final CookiesService cookiesService;

    // Login Users
    public LoginResponse loginUsers(@NotBlank(message = "Username is needed") String username, @NotBlank(message = "Password is needed") String password, HttpServletResponse response, HttpServletRequest request) {

        try {

            String ipAddress = getClientIpAddress(request);
            String userAgent = request.getHeader("User-Agent");


            // Check if username or password is blank or null
            if (username == null || username.isBlank() || password == null || password.isBlank()) {
                log.error("Username or password is blank");
                saveLoginEvent(null, "FAILED_LOGIN", "Blank username or password", ipAddress, userAgent);
                throw new BadRequestException("Username or password cannot be blank");
            }

            // check if user is existing in the database
            AuthUserCredentials user = userRepository.findByEmailOrPhoneNumber(username, username)
                    .orElseThrow(() -> {
                        log.error("User not found with username: {}", username);
                        saveLoginEvent(null, "FAILED_LOGIN", "User not found", ipAddress, userAgent);
                        return new BadRequestException("Invalid username or password");
                    });

            // check password with hashed password in the database
            if (!passwordEncoder.matches(password, user.getPasswordHash())) {
                log.error("Invalid password for user: {}", username);
                saveLoginEvent(user, "FAILED_LOGIN", "Invalid password attempt", ipAddress, userAgent);
                throw new BadRequestException("Invalid credentials");
            }

            // Check if user account is verified
            if (!isUserVerified(user)) {
                log.error("User account not verified: {}", username);
                saveLoginEvent(user, "FAILED_LOGIN", "Account not verified", ipAddress, userAgent);
                throw new ForbiddenException("Account not verified");
            }

            // check user status ( suspended, locked)
            if (Set.of(AuthUserCredentials.Status.LOCKED, AuthUserCredentials.Status.SUSPENDED)
                    .contains(user.getStatus())) {
                log.error("User account is locked or suspended: {}", username);
                saveLoginEvent(user, "FAILED_LOGIN", "Account is locked or suspended", ipAddress, userAgent);
                throw new ForbiddenException("Account is blocked or suspended");
            }

            // Generate access token (7 days) and refresh token (30 days)
            String accessToken = jwtService.generateAccessToken(user);
            String refreshToken = jwtService.generateRefreshToken(user);

            // Save tokens in database
            tokenService.saveAccessToken(user.getAuthUserId(), accessToken);
            tokenService.saveRefreshToken(user.getAuthUserId(), refreshToken);

            // Set HttpOnly cookies
            cookiesService.setAccessTokenCookie(response, accessToken);
            cookiesService.setRefreshTokenCookie(response, refreshToken);

            // Save successful login log
            saveLoginEvent(user, "SUCCESSFUL_LOGIN", "User logged in successfully", ipAddress, userAgent);

            // Update last login timestamp
            user.setLastLoginAt(LocalDateTime.now());
            userRepository.save(user);

            // Prepare response
            LoginResponse loginResponse = new LoginResponse();
            loginResponse.setMessage("Login successful");
            loginResponse.setUsername(user.getUsername());
            loginResponse.setEmail(user.getEmail());
            loginResponse.setPhoneNumber(user.getPhoneNumber());
            loginResponse.setStatus(user.getStatus().name());
            loginResponse.setRole(user.getStatus().name());
            loginResponse.setStatusCode("200");

            log.info("User {} logged in successfully", username);
            return loginResponse;
        } catch (RuntimeException e) {
            throw new RuntimeException(e);
        }
    }

    // Check if user is verified
    private boolean isUserVerified(AuthUserCredentials user) {
        return user.isEmailVerified() || user.isPhoneVerified();
    }

    // Save login event into database
    public void saveLoginEvent(AuthUserCredentials user, String eventType, String eventData, String ipAddress, String userAgent) {
        AuthSecurityEvent loginEvent = AuthSecurityEvent.builder()
                .authUser(user)
                .eventType(eventType)
                .eventData(eventData)
                .eventTime(LocalDateTime.now())
                .ipAddress(ipAddress)
                .userAgent(userAgent)
                .build();

        try {
            AuthSecurityEvent savedEvent = securityEvents.save(loginEvent);
            log.info("Saved login event with id: {}", savedEvent.getEventId());
        } catch (Exception e) {
            log.error("Failed to save security event: {}", e.getMessage());
        }
    }

    // Refresh Access Token
    @Transactional
    public String refreshAccessToken(String refreshToken, HttpServletResponse response, HttpServletRequest request) {

        String ipAddress = getClientIpAddress(request);
        String userAgent = request.getHeader("User-Agent");

        try {
            // Validate refresh token
            if (!tokenService.isTokenValid(refreshToken)) {
                log.error("Invalid or expired refresh token");
                throw new ForbiddenException("Invalid or expired refresh token, Please Login again");
            }

            // Decode token to get user ID
            String userId = jwtService.extractUserId(refreshToken);

            // Fetch user from database
            AuthUserCredentials user = userRepository.findById(java.util.UUID.fromString(userId))
                    .orElseThrow(() -> {
                        log.error("User not found with ID: {}", userId);
                        return new BadRequestException("User not found");
                    });

            // Check if user is still active
            if (Set.of(AuthUserCredentials.Status.LOCKED, AuthUserCredentials.Status.SUSPENDED)
                    .contains(user.getStatus())) {
                log.error("User account is locked or suspended: {}", user.getUsername());
                saveLoginEvent(user, "FAILED_TOKEN_REFRESH", "Account is " + user.getStatus().name().toLowerCase(), ipAddress, userAgent);
                throw new ForbiddenException("Account is blocked or suspended");
            }

            // Generate new access token
            String newAccessToken = jwtService.generateAccessToken(user);

            // Save new access token in database
            tokenService.saveAccessToken(user.getAuthUserId(), newAccessToken);

            // Set new Cookies
            cookiesService.setAccessTokenCookie(response, newAccessToken);

            // Log token refresh event
            saveLoginEvent(user, "TOKEN_REFRESH_SUCCESS", "Tokens refreshed successfully", ipAddress, userAgent);

            log.info("Generated new access token for user ID: {}", userId);
            return newAccessToken;
        } catch ( Exception e) {
            log.error("Error refreshing access token: {}", e.getMessage());
            throw new BadRequestException("Error refreshing access token");
        }
    }

    @Transactional
    public void logout(String accessToken, String refreshToken, HttpServletRequest request, HttpServletResponse response) {
        String ipAddress = getClientIpAddress(request);
        String userAgent = request.getHeader("User-Agent");

        try {
            // Extract user ID from access token
            String userId = jwtService.extractUserId(accessToken);

            // Fetch user
            AuthUserCredentials user = userRepository.findById(java.util.UUID.fromString(userId))
                    .orElse(null);

            // Revoke both tokens
            if (accessToken != null) {
                tokenService.revokeToken(accessToken);
            }
            if (refreshToken != null) {
                tokenService.revokeToken(refreshToken);
            }

            // Clear cookies
            cookiesService.clearAllTokenCookies(response);

            // Log logout event
            saveLoginEvent(user, "LOGOUT_SUCCESS", "User logged out successfully", ipAddress, userAgent);

            log.info("User {} logged out successfully", user != null ? user.getUsername() : "unknown");

        } catch (Exception e) {
            log.error("Error during logout: {}", e.getMessage());
            saveLoginEvent(null, "LOGOUT_FAILED", "Error: " + e.getMessage(), ipAddress, userAgent);
            // Still clear cookies even if error
            cookiesService.clearAllTokenCookies(response);
        }

    }

    @Transactional
    public void forceLogoutAllSessions(String userId, String reason) {
        try {
            // Revoke all tokens for the user
            tokenService.revokeAllUserTokens(java.util.UUID.fromString(userId));

            // Fetch user
            AuthUserCredentials user = userRepository.findById(java.util.UUID.fromString(userId))
                    .orElse(null);

            // Log forced logout event
            saveLoginEvent(user, "FORCED_LOGOUT", "All sessions terminated. Reason: " + reason, "SYSTEM", "SYSTEM");

            log.info("All sessions terminated for user ID: {}", userId);

        } catch (Exception e) {
            log.error("Error forcing logout for user {}: {}", userId, e.getMessage());
        }
    }

    // Get client IP address from request
    private String getClientIpAddress(HttpServletRequest request) {
        String xForwardedFor = request.getHeader("X-Forwarded-For");
        if (xForwardedFor != null && !xForwardedFor.isEmpty()) {
            return xForwardedFor.split(",")[0].trim();
        }

        String xRealIp = request.getHeader("X-Real-IP");
        if (xRealIp != null && !xRealIp.isEmpty()) {
            return xRealIp;
        }

        return request.getRemoteAddr();
    }
}

