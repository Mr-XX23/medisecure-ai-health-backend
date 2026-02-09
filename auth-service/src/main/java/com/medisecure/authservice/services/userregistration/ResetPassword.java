package com.medisecure.authservice.services.userregistration;

import com.medisecure.authservice.dto.userregistrations.RegistrationResponse;
import com.medisecure.authservice.exceptions.BadRequestException;
import com.medisecure.authservice.models.AuthUserCredentials;
import com.medisecure.authservice.models.PasswordResetToken;
import com.medisecure.authservice.repository.PasswordResetTokenRepository;
import com.medisecure.authservice.repository.UserRepository;
import com.medisecure.authservice.services.AuthSecurityEventService;
import com.medisecure.authservice.services.EmailService;
import com.medisecure.authservice.services.OtpService;
import com.medisecure.authservice.services.SmsService;
import jakarta.persistence.EntityManager;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.UUID;
import java.util.regex.Pattern;

@Service
@RequiredArgsConstructor
@Slf4j
public class ResetPassword {

    private final AuthSecurityEventService securityEventService;
    private final UserRepository userRepository;
    private final OtpService otpService;
    private final EmailService emailService;
    private final SmsService smsService;
    private final PasswordEncoder passwordEncoder;
    private final PasswordResetTokenRepository passwordResetTokenRepository;
    private final EntityManager entityManager;

    private static final Pattern EMAIL_PATTERN = Pattern.compile(
            "^[A-Za-z0-9+_.-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$"
    );

    private static final Pattern PHONE_PATTERN = Pattern.compile("^\\+?[1-9]\\d{1,14}$");

    private static final Pattern PASSWORD_PATTERN = Pattern.compile(
            "^(?=.*[a-z])(?=.*[A-Z])(?=.*\\d)(?=.*[@$!%*?&])[A-Za-z\\d@$!%*?&]{8,}$"
    );

    /**
     * Initiate password reset for user using email or phone.
     */
    @Transactional
    public RegistrationResponse resetPassword(String userContact, HttpServletRequest httpRequest) {

        securityEventService.logSecurityEvent(
                null,
                "PASSWORD_RESET_ATTEMPT",
                "Password reset initiated for: " + maskContact(userContact),
                httpRequest);

        // Validate contact format
        ContactType contactType = determineContactType(userContact);
        if (contactType == null) {
            securityEventService.logSecurityEvent(
                    null,
                    "PASSWORD_RESET_FAILED",
                    "Invalid contact format provided",
                    httpRequest);
            throw new BadRequestException("Invalid email or phone number format");
        }

        // Find user
        AuthUserCredentials user = userRepository.findByEmailOrPhoneNumber(userContact, userContact)
                .orElseThrow(() -> {
                    log.warn("Password reset attempted for non-existent user: {}", maskContact(userContact));
                    securityEventService.logSecurityEvent(
                            null,
                            "PASSWORD_RESET_FAILED",
                            "Password reset attempted for non-existent user",
                            httpRequest);
                    return new BadRequestException("If this account exists, you will receive a reset code");
                });

        // Check user status
        if (user.getStatus() == AuthUserCredentials.Status.SUSPENDED ||
                user.getStatus() == AuthUserCredentials.Status.LOCKED) {
            securityEventService.logSecurityEvent(
                    user,
                    "PASSWORD_RESET_FAILED",
                    "Password reset attempted for suspended/locked account",
                    httpRequest);
            throw new BadRequestException("Account is suspended or locked");
        }

        // Check rate limiting
        if (isPasswordResetRateLimited(user.getAuthUserId())) {
            securityEventService.logSecurityEvent(
                    user,
                    "PASSWORD_RESET_RATE_LIMITED",
                    "Too many password reset attempts",
                    httpRequest);
            throw new BadRequestException("Too many password reset attempts. Please try again later.");
        }

        // Invalidate any existing tokens
        invalidateExistingTokens(user.getAuthUserId());

        if (contactType == ContactType.EMAIL) {
            return handleEmailReset(user, httpRequest);
        } else {
            return handlePhoneReset(user, httpRequest);
        }
    }

    /**
     * Confirm password reset using token and new password.
     */
    @Transactional
    public RegistrationResponse confirmPasswordReset(
            String token,
            String newPassword,
            HttpServletRequest httpRequest) {

        securityEventService.logSecurityEvent(
                null,
                "PASSWORD_RESET_CONFIRM_ATTEMPT",
                "Password reset confirmation attempted",
                httpRequest);

        // Validate password strength
        if (!isValidPassword(newPassword)) {
            securityEventService.logSecurityEvent(
                    null,
                    "PASSWORD_RESET_CONFIRM_FAILED",
                    "Weak password provided",
                    httpRequest);
            throw new BadRequestException(
                    "Password must be at least 8 characters with uppercase, lowercase, number, and special character");
        }

        // Find and validate token
        PasswordResetToken resetToken = passwordResetTokenRepository.findByToken(token)
                .orElseThrow(() -> {
                    log.warn("Invalid password reset token used");
                    securityEventService.logSecurityEvent(
                            null,
                            "PASSWORD_RESET_CONFIRM_FAILED",
                            "Invalid reset token",
                            httpRequest);
                    return new BadRequestException("Invalid or expired reset token");
                });

        // Check expiration
        if (resetToken.getExpiryDate().isBefore(LocalDateTime.now())) {
            securityEventService.logSecurityEvent(
                    resetToken.getUser(),
                    "PASSWORD_RESET_CONFIRM_FAILED",
                    "Expired reset token used",
                    httpRequest);
            passwordResetTokenRepository.delete(resetToken);
            throw new BadRequestException("Invalid or expired reset token");
        }

        AuthUserCredentials user = resetToken.getUser();

        // Check if new password is same as old
        if (passwordEncoder.matches(newPassword, user.getPasswordHash())) {
            securityEventService.logSecurityEvent(
                    user,
                    "PASSWORD_RESET_CONFIRM_FAILED",
                    "New password same as old password",
                    httpRequest);
            throw new BadRequestException("New password must be different from current password");
        }

        // Update password
        user.setPasswordHash(passwordEncoder.encode(newPassword));
        user.setUpdatedAt(LocalDateTime.now());
        userRepository.save(user);

        // Delete token
        passwordResetTokenRepository.delete(resetToken);

        entityManager.flush();

        securityEventService.logSecurityEvent(
                user,
                "PASSWORD_RESET_SUCCESS",
                "Password reset completed successfully",
                httpRequest);

        log.info("Password reset successful for user ID: {}", user.getAuthUserId());

        return RegistrationResponse.builder()
                .success(true)
                .message("Password reset successfully. Please login with your new password.")
                .build();
    }


    private RegistrationResponse handleEmailReset(AuthUserCredentials user, HttpServletRequest httpRequest) {
        try {
            // Generate and hash token
            String resetToken = UUID.randomUUID().toString();
            String tokenHash = passwordEncoder.encode(resetToken);

            // Save hashed token
            PasswordResetToken passwordResetToken = new PasswordResetToken();
            passwordResetToken.setToken(tokenHash);
            passwordResetToken.setUser(user);
            passwordResetToken.setExpiryDate(LocalDateTime.now().plusHours(1));
            passwordResetTokenRepository.save(passwordResetToken);

            entityManager.flush();

            // Send email (async)
            emailService.sendPasswordResetEmail(user.getEmail(), resetToken, user.getAuthUserId())
                    .exceptionally(ex -> {
                        log.error("Failed to send password reset email to: {}", user.getEmail(), ex);
                        return null;
                    });

            securityEventService.logSecurityEvent(
                    user,
                    "PASSWORD_RESET_EMAIL_SENT",
                    "Password reset email sent",
                    httpRequest);

            return RegistrationResponse.builder()
                    .success(true)
                    .email(user.getEmail())
                    .message("If this email exists in our system, you will receive a password reset link")
                    .build();

        } catch (Exception e) {
            log.error("Error sending password reset email: {}", e.getMessage(), e);
            securityEventService.logSecurityEvent(
                    user,
                    "PASSWORD_RESET_EMAIL_FAILED",
                    "Failed to send password reset email",
                    httpRequest);
            throw new RuntimeException("Unable to process password reset. Please try again later.");
        }
    }

    private RegistrationResponse handlePhoneReset(AuthUserCredentials user, HttpServletRequest httpRequest) {
        try {
            // Generate OTP
            String otp = otpService.generatePasswordResetOtp(user.getAuthUserId());

            // Send SMS (async)
            smsService.sendPasswordResetSms(user.getPhoneNumber(), otp, user.getAuthUserId())
                    .exceptionally(ex -> {
                        log.error("Failed to send password reset SMS to: {}", user.getPhoneNumber(), ex);
                        return null;
                    });

            securityEventService.logSecurityEvent(
                    user,
                    "PASSWORD_RESET_SMS_SENT",
                    "Password reset OTP sent via SMS",
                    httpRequest);

            return RegistrationResponse.builder()
                    .success(true)
                    .message("If this phone number exists in our system, you will receive a password reset OTP")
                    .build();

        } catch (Exception e) {
            log.error("Error sending password reset SMS: {}", e.getMessage(), e);
            securityEventService.logSecurityEvent(
                    user,
                    "PASSWORD_RESET_SMS_FAILED",
                    "Failed to send password reset SMS",
                    httpRequest);
            throw new RuntimeException("Unable to process password reset. Please try again later.");
        }
    }

    private ContactType determineContactType(String contact) {
        if (contact == null || contact.trim().isEmpty()) {
            return null;
        }

        String trimmed = contact.trim();

        if (EMAIL_PATTERN.matcher(trimmed).matches()) {
            return ContactType.EMAIL;
        } else if (PHONE_PATTERN.matcher(trimmed).matches()) {
            return ContactType.PHONE;
        }

        return null;
    }

    private boolean isValidPassword(String password) {
        if (password == null || password.length() < 8) {
            return false;
        }
        return PASSWORD_PATTERN.matcher(password).matches();
    }

    private boolean isPasswordResetRateLimited(UUID userId) {
        LocalDateTime oneHourAgo = LocalDateTime.now().minusHours(1);
        long recentAttempts = passwordResetTokenRepository
                .countByUser_AuthUserIdAndExpiryDateAfter(userId, oneHourAgo);
        return recentAttempts >= 3; // Max 3 reset attempts per hour
    }

    private void invalidateExistingTokens(UUID userId) {
        passwordResetTokenRepository.deleteAllByUser_AuthUserId(userId);
    }

    private String maskContact(String contact) {
        if (contact == null || contact.length() < 4) {
            return "****";
        }
        if (contact.contains("@")) {
            String[] parts = contact.split("@");
            return parts[0].substring(0, Math.min(2, parts[0].length())) + "***@" + parts[1];
        } else {
            return contact.substring(0, Math.min(3, contact.length())) + "****";
        }
    }

    private enum ContactType {
        EMAIL, PHONE
    }
}
