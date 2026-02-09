package com.medisecure.authservice.controllers;

import com.medisecure.authservice.dto.loginregistration.OAuth2LoginResponse;
import com.medisecure.authservice.services.OAuth2Service;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/auth/oauth2")
@RequiredArgsConstructor
public class OAuth2Controller {

    private final OAuth2Service oauth2Service;

//    @GetMapping("/callback/google")
//    public ResponseEntity<OAuth2LoginResponse> googleCallback(
//            @AuthenticationPrincipal OAuth2User oauth2User,
//            HttpServletResponse response,
//            HttpServletRequest request) {
//
//        OAuth2LoginResponse loginResponse = oauth2Service.processOAuth2Login(
//                oauth2User, response, request);
//
//        return ResponseEntity.ok(loginResponse);
//    }
}
