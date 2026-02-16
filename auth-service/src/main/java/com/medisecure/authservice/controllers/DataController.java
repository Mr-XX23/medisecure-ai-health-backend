package com.medisecure.authservice.controllers;

import com.medisecure.authservice.dto.user.UserDetailsRequest;
import com.medisecure.authservice.dto.user.UserDetailsResponse;
import com.medisecure.authservice.services.user.UserDetailsService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

/**
 * Controller for user data retrieval and verification with high security
 */
@RestController
@RequestMapping("/api/v1/auth/users")
@RequiredArgsConstructor
@Slf4j
@Validated
public class DataControllar {

    private final UserDetailsService userDetailsService;

    @GetMapping("/me")
    public ResponseEntity<UserDetailsResponse> getCurrentUser(HttpServletRequest request) {
        log.info("Request to get current user details from IP: {}", getClientIp(request));
        UserDetailsResponse response = userDetailsService.getCurrentUserDetails(request);
        return ResponseEntity.ok(response);
    }

    @GetMapping("/{userId}")
    public ResponseEntity<UserDetailsResponse> getUserById(
            @PathVariable @NotBlank(message = "User ID is required") String userId,
            HttpServletRequest request) {
        log.info("Request to get user details for userId: {} from IP: {}", userId, getClientIp(request));
        UserDetailsResponse response = userDetailsService.getUserDetailsById(userId, request);
        return ResponseEntity.ok(response);
    }

    @PostMapping("/search")
    public ResponseEntity<UserDetailsResponse> searchUser(
            @Valid @RequestBody UserDetailsRequest userRequest,
            HttpServletRequest request) {
        log.info("Request to search user from IP: {}", getClientIp(request));
        UserDetailsResponse response = userDetailsService.getUserDetails(userRequest, request);
        return ResponseEntity.ok(response);
    }

    @GetMapping("/verify/{userId}")
    public ResponseEntity<UserDetailsResponse> verifyUserStatus(
            @PathVariable @NotBlank(message = "User ID is required") String userId) {
        log.info("Request to verify user status for userId: {}", userId);
        UserDetailsResponse response = userDetailsService.verifyUserStatus(userId);
        return ResponseEntity.ok(response);
    }

    @GetMapping("/by-email/{email}")
    @PreAuthorize("hasAnyRole('ADMIN', 'SUPER_ADMIN')")
    public ResponseEntity<UserDetailsResponse> getUserByEmail(
            @PathVariable @NotBlank(message = "Email is required") String email,
            HttpServletRequest request) {
        log.info("Admin request to get user by email from IP: {}", getClientIp(request));
        UserDetailsRequest userRequest = new UserDetailsRequest();
        userRequest.setEmail(email);
        UserDetailsResponse response = userDetailsService.getUserDetails(userRequest, request);
        return ResponseEntity.ok(response);
    }

    @GetMapping("/by-phone/{phoneNumber}")
    @PreAuthorize("hasAnyRole('ADMIN', 'SUPER_ADMIN')")
    public ResponseEntity<UserDetailsResponse> getUserByPhone(
            @PathVariable @NotBlank(message = "Phone number is required") String phoneNumber,
            HttpServletRequest request) {
        log.info("Admin request to get user by phone from IP: {}", getClientIp(request));
        UserDetailsRequest userRequest = new UserDetailsRequest();
        userRequest.setPhoneNumber(phoneNumber);
        UserDetailsResponse response = userDetailsService.getUserDetails(userRequest, request);
        return ResponseEntity.ok(response);
    }

    private String getClientIp(HttpServletRequest request) {
        String xForwardedFor = request.getHeader("X-Forwarded-For");
        if (xForwardedFor != null && !xForwardedFor.isEmpty()) {
            return xForwardedFor.split(",")[0].trim();
        }
        return request.getRemoteAddr();
    }
}
