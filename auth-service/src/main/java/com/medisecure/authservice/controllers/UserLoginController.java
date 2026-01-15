package com.medisecure.authservice.controllers;

import com.medisecure.authservice.dto.CookieUtil;
import com.medisecure.authservice.dto.loginregistration.LoginRequest;
import com.medisecure.authservice.dto.loginregistration.LoginResponse;
import com.medisecure.authservice.services.UserLoginService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/auth")
@RequiredArgsConstructor
public class UserLoginController {

    private final UserLoginService userLoginService;

    /**
     * Login a user with username and password.
     * @param response HttpServletResponse, request HttpServletRequest, username String, password String , The registration request containing user details.
     * @return A LoginResponse entity with login status, jwt token and details.
     */
    @PostMapping("/login")
    public ResponseEntity<LoginResponse> loginUser(HttpServletResponse response, HttpServletRequest request, @RequestBody @Valid LoginRequest loginRequest) {
        LoginResponse loginResponse = userLoginService.loginUsers(loginRequest.getUsername(),  loginRequest.getPassword(), response, request);
       return ResponseEntity.ok(loginResponse);
    }

    /**
     * Refresh access token using refresh token.
     * @param response HttpServletResponse, request HttpServletRequest
     * @return A response entity with new access token.
     */
    @PostMapping("/refresh")
    public ResponseEntity<String> refreshToken(HttpServletRequest request, HttpServletResponse response) {


        String refreshToken = CookieUtil.getCookieValue(request, "refresh_token")
                .orElseThrow(() -> new IllegalArgumentException("Refresh token not found"));

        String newAccessToken = userLoginService.refreshAccessToken(refreshToken, response, request);
        return ResponseEntity.ok(newAccessToken);
    }

    /**
     * Logout user by invalidating tokens.
     * @param response HttpServletResponse, request HttpServletRequest
     * @return A response entity with logout status.
     */
    @GetMapping("/logout")
    public ResponseEntity<String> logout(
            HttpServletRequest request,
            HttpServletResponse response) {

        String accessToken = CookieUtil.getCookieValue(request, "access_token").orElse(null);
        String refreshToken = CookieUtil.getCookieValue(request, "refresh_token").orElse(null);

        userLoginService.logout(accessToken, refreshToken, request, response);

        return ResponseEntity.ok("Logged out successfully");
    }

    /**
     * Logout user by invalidating tokens.
     * @param userId The ID of the user to force logout.
     * @param reason The reason for force logout.
     * @return A response entity with logout status.
     */
    @PostMapping("/force-logout/{userId}")
    public ResponseEntity<String> forceLogout(
            @PathVariable String userId,
            @RequestParam(defaultValue = "Admin action") String reason) {

        userLoginService.forceLogoutAllSessions(userId, reason);

        return ResponseEntity.ok("All sessions terminated for user");
    }
}
