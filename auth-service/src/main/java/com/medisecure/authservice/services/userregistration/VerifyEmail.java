package com.medisecure.authservice.services.userregistration;

import com.medisecure.authservice.dto.userregistrations.RegistrationResponse;
import com.medisecure.authservice.exceptions.BadRequestException;
import com.medisecure.authservice.models.AuthUserCredentials;
import com.medisecure.authservice.models.OtpEventLog;
import com.medisecure.authservice.repository.OtpEventLogRepository;
import com.medisecure.authservice.repository.UserRepository;
import com.medisecure.authservice.services.AuthSecurityEventService;
import com.medisecure.authservice.services.HashFormater;
import jakarta.persistence.EntityManager;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.constraints.NotBlank;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;

@Service
@RequiredArgsConstructor
@Slf4j
public class VerifyEmail {

    private final UserRepository userRepository;
    private final OtpEventLogRepository otpEventLogRepository;
    private final HashFormater hashFormater;
    private final EntityManager entityManager;
    private final AuthSecurityEventService securityEventService;

    /**
     * Verify user's email address using the verification token.
     *
     * @param token The email verification token.
     * @return A response entity with verification status.
     */

    @Transactional
    public RegistrationResponse verifyEmail(@NotBlank(message = "Token is required") String token, HttpServletRequest httpRequest) {

        // Log security even
        securityEventService.logSecurityEvent(
                null,
                "EMAIL_VERIFICATION",
                "An email verification attempt is made for activations of account.",
                httpRequest);

        // Validate token is not empty
        if (token == null || token.isBlank()) {
            securityEventService.logSecurityEvent(
                    null,
                    "EMAIL_VERIFICATION_FAILED",
                    "Email verification failed: empty token.",
                    httpRequest);
            throw new BadRequestException("Token cannot be empty");
        }

        try {

            // Hash the token to match stored hash
            String tokenHash = hashFormater.hashWithSHA256(token);

            // Find OTP log entry

            OtpEventLog otpLog = otpEventLogRepository
                    .findFirstByOtpTypeAndOtpCodeAndVerifiedAndExpiresAtAfter(
                            "EMAIL_VERIFICATION",
                            tokenHash,
                            false,
                            LocalDateTime.now()
                    )
                    .orElse(null);

            if (otpLog == null) {

                // Log security even
                securityEventService.logSecurityEvent(
                        null,
                        "EMAIL_VERIFICATION",
                        "Invalid email verification attempt.",
                        httpRequest);

                throw new BadRequestException("Invalid token or Cannot be empty");
            }

            // Get user
            AuthUserCredentials user = otpLog.getAuthUser();

            // Check if email is already verified
            if (user.isEmailVerified()) {
                log.info("Email already verified for user: {}", user.getAuthUserId());

                securityEventService.logSecurityEvent(
                        user,
                        "EMAIL_VERIFICATION_DUPLICATE",
                        "Email verification attempted for already verified email.",
                        httpRequest);

                return RegistrationResponse.builder()
                        .success(true)
                        .message("Email is already verified" +
                                (user.getStatus() == AuthUserCredentials.Status.ACTIVE
                                        ? ". Your account is active."
                                        : ". Please verify your phone number to activate your account."))
                        .email(user.getEmail())
                        .username(user.getUsername())
                        .userId(user.getAuthUserId().toString())
                        .build();
            }

            // Update user verification status
            user.setEmailVerified(true);

            // If user only has email (not BOTH), activate account
            if (user.getLoginType() == AuthUserCredentials.LoginType.EMAIL) {
                user.setStatus(AuthUserCredentials.Status.ACTIVE);
            }

            // If user has BOTH and phone is already verified, activate account
            if (user.getLoginType() == AuthUserCredentials.LoginType.BOTH && user.isPhoneVerified()) {
                user.setStatus(AuthUserCredentials.Status.ACTIVE);
            }

            // Update the updatedAt timestamp
            user.setUpdatedAt(LocalDateTime.now());

            // Mark OTP as verified
            otpLog.setVerified(true);

            // Save changes to database with validation
            try {
                userRepository.save(user);
                otpEventLogRepository.save(otpLog);

                // Force flush to catch database errors immediately
                entityManager.flush();

                log.info("Email verified successfully for user: {}", user.getAuthUserId());

            } catch (DataIntegrityViolationException e) {
                log.error("Database constraint violation during email verification: {}", e.getMessage());

                securityEventService.logSecurityEvent(
                        user,
                        "EMAIL_VERIFICATION_FAILED",
                        "Email verification failed: database constraint violation.",
                        httpRequest);

                throw new RuntimeException("Failed to verify email. Please try again.");

            } catch (Exception e) {
                log.error("Database error during email verification for user {}: {}",
                        user.getAuthUserId(), e.getMessage());

                securityEventService.logSecurityEvent(
                        user,
                        "EMAIL_VERIFICATION_FAILED",
                        "Email verification failed: database error.",
                        httpRequest);

                throw new RuntimeException("Failed to verify email. Please try again.");
            }

            // Log success event
            securityEventService.logSecurityEvent(
                    user,
                    "EMAIL_VERIFICATION_SUCCESS",
                    "Email verified successfully" + (user.getStatus() == AuthUserCredentials.Status.ACTIVE
                            ? ". Account is now active."
                            : ". Phone verification pending to activate account."),
                    httpRequest);


            return RegistrationResponse.builder()
                    .success(true)
                    .message("Email verified successfully" +
                            (user.getStatus() == AuthUserCredentials.Status.ACTIVE
                                    ? ". Your account is now active."
                                    : ". Please verify your phone number to activate your account to access full features."))
                    .email(user.getEmail())
                    .username(user.getUsername())
                    .userId(user.getAuthUserId().toString())
                    .build();
        } catch (Exception e) {
            log.error("Error verifying email: {}", e.getMessage());

            // Log security even
            securityEventService.logSecurityEvent(
                    null,
                    "EMAIL_VERIFICATION",
                    "Error verifying email.",
                    httpRequest);

            throw new RuntimeException("Error verifying email. Please try again.");
        }
    }


}
