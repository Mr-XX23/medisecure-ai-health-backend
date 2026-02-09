package com.medisecure.authservice.controllers;

import com.medisecure.authservice.dto.email.EmailVerificationRequest;
import com.medisecure.authservice.dto.passwordreset.PasswordResetConfirmRequest;
import com.medisecure.authservice.dto.passwordreset.PasswordResetRequest;
import com.medisecure.authservice.dto.phone.PhoneVerificationRequest;
import com.medisecure.authservice.dto.userregistrations.RegistrationRequest;
import com.medisecure.authservice.dto.userregistrations.RegistrationResponse;
import com.medisecure.authservice.services.userregistration.*;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/auth")
@RequiredArgsConstructor
public class UserRegistration {

    private final Registration registrationService;
    private final SendEmailVerification sendEmailVerification;
    private final SendPhoneVerification sendPhoneVerification;
    private final VerifyEmail verifyEmail;
    private final VerifyPhone verifyPhone;
    private final ResetPassword resetPassword;


    /**
     * Register a new user with email or phone number.
     * @param request The registration request containing user details.
     * @return A response entity with registration status.
     */
    @PostMapping("/register")
    public ResponseEntity<RegistrationResponse> registerUser(HttpServletRequest httpRequest, @Valid @RequestBody RegistrationRequest request) {

        RegistrationResponse response = registrationService.registerUser(request, httpRequest);
        return ResponseEntity.ok(response);
    }

    /**
     * Verify user's email address using the verification token.
     * @param request The verification request containing the userId.
     * @return A response entity with verification status.
     */
    @PostMapping("/send-email-verification")
    public ResponseEntity<RegistrationResponse> sendEmailVerification(@Valid @RequestBody EmailVerificationRequest request, HttpServletRequest httpRequest) {
        RegistrationResponse response = sendEmailVerification.sendEmailVerification(request.getUserId(), httpRequest);
        return ResponseEntity.ok(response);
    }

    /**
     * Verify user's phone number using the OTP.
     * @param request The verification request containing userId.
     * @return A response entity with verification status.
     */
    @PostMapping("/send-phone-verification")
    public ResponseEntity<RegistrationResponse> sendPhoneVerification(@Valid @RequestBody PhoneVerificationRequest request, HttpServletRequest httpRequest) {
        RegistrationResponse response = sendPhoneVerification.sendPhoneVerification(request.getUserId(), httpRequest);
        return ResponseEntity.ok(response);
    }

    /**
     * Verify user's email address using the verification token.
     * @param token The email verification token.
     * @return A response entity with verification status.
     */
    @GetMapping("/verify-email")
    public ResponseEntity<RegistrationResponse> verifyEmail(@RequestParam("token") @NotBlank(message = "Token is required") String token, HttpServletRequest httpRequest) {

        RegistrationResponse response = verifyEmail.verifyEmail(token, httpRequest);
        HttpStatus status = response.isSuccess() ? HttpStatus.OK : HttpStatus.BAD_REQUEST;
        return ResponseEntity.status(status).body(response);
    }

    /**
     * Verify user's phone number using the OTP.
     * @param userId The user ID.
     * @param otp The OTP code.
     * @return A response entity with verification status.
     */
    @PostMapping("/verify-phone")
    public ResponseEntity<RegistrationResponse> verifyPhone(
            @RequestBody @NotBlank(message = "OTP is required") String otp,
            @NotBlank(message = "ID is required") String userId, HttpServletRequest httpRequest) {

        RegistrationResponse response = verifyPhone.verifyPhone(userId, otp, httpRequest);
        HttpStatus status = response.isSuccess() ? HttpStatus.OK : HttpStatus.BAD_REQUEST;
        return ResponseEntity.status(status).body(response);

    }

    /**
     * Password reset for user using email or phone.
     * @param request The password reset request containing email or phone number.
     * @return A response entity with verification status.
     */
    @PostMapping("/reset-password")
    public ResponseEntity<RegistrationResponse> resetPassword(
            @Valid @RequestBody PasswordResetRequest request, HttpServletRequest httpRequest) {
        RegistrationResponse response = resetPassword.resetPassword(request.getUserContact(), httpRequest);
        return ResponseEntity.ok(response);
    }

    /**
     * Confirm password reset for user using email or phone.
     * @param token The password reset token.
     * @param request The confirmation request containing new password.
     * @return A response entity with verification status.
     */
    @PostMapping("/confirm-reset")
    public ResponseEntity<RegistrationResponse> confirmPasswordReset(
            @RequestParam("token") @NotBlank(message = "Token is required") String token,
            @Valid @RequestBody PasswordResetConfirmRequest request, HttpServletRequest httpRequest) {

        RegistrationResponse response = resetPassword.confirmPasswordReset(token, request.getNewPassword(), httpRequest);
        HttpStatus status = response.isSuccess() ? HttpStatus.OK : HttpStatus.BAD_REQUEST;
        return ResponseEntity.status(status).body(response);
    }

}
