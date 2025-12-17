package com.medisecure.authservice.services;

import com.medisecure.authservice.dto.userregistrations.RegistrationRequest;
import com.medisecure.authservice.dto.userregistrations.RegistrationResponse;
import com.medisecure.authservice.exceptions.BadRequestException;
import com.medisecure.authservice.models.AuthUserCredentials;
import com.medisecure.authservice.models.OtpEventLog;
import com.medisecure.authservice.models.PasswordResetToken;
import com.medisecure.authservice.repository.OtpEventLogRepository;
import com.medisecure.authservice.repository.PasswordResetTokenRepository;
import com.medisecure.authservice.repository.UserRepository;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.security.SecureRandom;
import java.time.LocalDateTime;
import java.util.Random;
import java.util.UUID;

@Service
@RequiredArgsConstructor
@Slf4j
public class UserRegistrationService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final OtpService otpService;
    private final EmailService emailService;
    private final SmsService smsService;
    private final Random random = new SecureRandom();
    private static final String PREFIX = "MS_";
    private final OtpEventLogRepository otpEventLogRepository;
    private final HashFormater hashFormater;
    private final PasswordResetTokenRepository passwordResetTokenRepository;


    /**
     * Register a new user with email or phone number.
     * @param request The registration request containing user details.
     * @return A response entity with registration status.
     */

    @Transactional
    public RegistrationResponse registerUser(@Valid RegistrationRequest request) {

        try {
            // Validate that at least one contact method is provided
            if (request.getEmail() == null && request.getPhoneNumber() == null) {
                throw new BadRequestException("Either email or phone number must be provided");
            }

            // Determine primary login type
            AuthUserCredentials.LoginType loginType;
            if (request.getEmail() != null && request.getPhoneNumber() != null) {
                loginType = AuthUserCredentials.LoginType.BOTH;
            } else if (request.getEmail() != null) {
                loginType = AuthUserCredentials.LoginType.EMAIL;
            } else {
                loginType = AuthUserCredentials.LoginType.PHONE;
            }

            // Check if user already exists (without revealing which field exists)
            boolean exists = ( request.getEmail() != null && userRepository.existsByEmail(request.getEmail()) )
                    || ( request.getPhoneNumber() != null && userRepository.existsByPhoneNumber(request.getPhoneNumber()) );

            if (exists) {
                log.warn("Registration attempt with existing credentials");
                // Return generic success response for privacy
                return buildGenericResponse(loginType);
            }


            // hash the password
            String passwordHash = passwordEncoder.encode(request.getPassword());


            // Create new auth user credentials
            AuthUserCredentials authUserCredentials = AuthUserCredentials.builder()
                    .username(generateUniqueUsername())
                    .email(request.getEmail() !=null ? request.getEmail() : "")
                    .phoneNumber(request.getPhoneNumber() != null ? request.getPhoneNumber() : "")
                    .passwordHash(passwordHash)
                    .loginType(loginType)
                    .status(AuthUserCredentials.Status.INACTIVE)
                    .isEmailVerified(false)
                    .isPhoneVerified(false)
                    .mfaEnabled(false)
                    .createdAt(LocalDateTime.now())
                    .updatedAt(LocalDateTime.now())
                    .build();

            // Save to database
            AuthUserCredentials savedUser;
            try {
                savedUser = userRepository.save(authUserCredentials);
            } catch (Exception e) {
                log.error("Error saving user: {}", e.getMessage());
                throw new RuntimeException("Failed to register user. Please try again.");
            }

            // Send verification
            try {
                if (loginType == AuthUserCredentials.LoginType.EMAIL || loginType == AuthUserCredentials.LoginType.BOTH) {
                    String verificationToken = otpService.generateEmailVerificationToken(savedUser.getAuthUserId());
                    emailService.sendVerificationEmail(savedUser.getEmail(), verificationToken, savedUser.getAuthUserId());
                } else {
                    String otp = otpService.generatePhoneOtp(savedUser.getAuthUserId());
                    smsService.sendOtpSms(savedUser.getPhoneNumber(), otp, savedUser.getAuthUserId());
                }
            } catch (Exception e) {
                log.error("Error sending verification: {}", e.getMessage());
                throw new RuntimeException("Failed to register user. Please try again.");
            }

            return RegistrationResponse.builder()
                    .success(true)
                    .message("Registration successful. Please verify your " + (loginType == AuthUserCredentials.LoginType.EMAIL ? "email." : (loginType == AuthUserCredentials.LoginType.BOTH) ? "email and phone number." : "phone number.") )
                    .username(savedUser.getUsername())
                    .userId(savedUser.getAuthUserId().toString())
                    .email(savedUser.getEmail())
                    .build();

        } catch ( Exception e ) {
            throw new RuntimeException("Failed to register user. Please try again.");
        }
    }

    /**
     * Builds a generic registration response to avoid revealing existing user details.
     * @param loginType The type of login used (email or phone).
     * @return A generic RegistrationResponse.
     */

    private RegistrationResponse buildGenericResponse(AuthUserCredentials.LoginType loginType) {
        String message = loginType == AuthUserCredentials.LoginType.EMAIL
                ? "Please verify your email to register your account. New user cannot be created with provided email" :
                loginType == AuthUserCredentials.LoginType.BOTH ?
                        "Please verify your email and phone number to register your account. New user cannot be created with provided credentials"
                : "Please verify your phone number to register your account. New user cannot be created with provided phone number";

        throw new BadRequestException(message);
    }

    /**
     * Generates a unique username with the format "MS_" followed by 8 random alphanumeric characters.
     * @return A unique username.
     */

    private String generateUniqueUsername() {
        String username;
        int attempts = 0;
        final int MAX_ATTEMPTS = 10;

        do {
            // Format: MU + 8 random alphanumeric characters
            String randomPart = generateRandomString(8);
            username = PREFIX + randomPart;
            attempts++;

            if (attempts >= MAX_ATTEMPTS) {
                // Fallback with timestamp if collision persists
                username = PREFIX + generateRandomString(6) + System.currentTimeMillis() % 10000;
            }
        } while (userRepository.existsByUsername(username));

        return username;
    }

    /**
     * Generates a random alphanumeric string of specified length.
     * @param length The length of the random string.
     * @return A random alphanumeric string.
     */

    private String generateRandomString(int length) {
        String chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
        StringBuilder sb = new StringBuilder(length);

        for (int i = 0; i < length; i++) {
            sb.append(chars.charAt(random.nextInt(chars.length())));
        }

        return sb.toString();
    }

    /**
     * Verifies user's email address using the verification token.
     * @param userId The email verification token.
     * @return A response entity with verification status.
     */

    @Transactional
    public RegistrationResponse sendEmailVerification(UUID userId) {
        try {
            AuthUserCredentials user = userRepository.findById(userId)
                    .orElseThrow(() -> new RuntimeException("User not found"));

            if (user.isEmailVerified()) {
                throw new BadRequestException("Email already verified");
            }

            String token = otpService.generateEmailVerificationToken(userId);
            emailService.sendVerificationEmail(user.getEmail(), token, userId);

            return RegistrationResponse.builder()
                    .success(true)
                    .email(user.getEmail())
                    .userId(user.getAuthUserId().toString())
                    .username(user.getUsername())
                    .message("Verification email sent successfully")
                    .build();

        } catch (Exception e) {
            log.error("Error sending verification email: {}", e.getMessage());
            throw new BadRequestException("Error sending verification email. Please try again.");
        }
    }

    /**
     * Verifies user's phone number using the OTP.
     * @param userId The ID of the user.
     * @return A response entity with verification status.
     */

    @Transactional
    public RegistrationResponse sendPhoneVerification(UUID userId) {

        log.info("Sending phone verification to user ID: {}", userId);

        try {
            AuthUserCredentials user = userRepository.findById(userId)
                    .orElseThrow(() -> new RuntimeException("User not found"));

            if (user.isPhoneVerified()) {
                throw new BadRequestException("Phone already verified");
            }

            if (user.getLoginType() == AuthUserCredentials.LoginType.BOTH && !user.isEmailVerified()) {
                throw new BadRequestException("Email should verified before phone verification");
            }

            String otp = otpService.generatePhoneOtp(userId);
            smsService.sendOtpSms(user.getPhoneNumber(), otp, userId);

            return RegistrationResponse.builder()
                    .success(true)
                    .username(user.getUsername())
                    .userId(user.getAuthUserId().toString())
                    .email(user.getEmail())
                    .message("OTP sent successfully")
                    .build();
        } catch (Exception e) {
            log.error("Error sending phone OTP: {}", e.getMessage());
            throw new RuntimeException("Error sending phone OTP. Please try again.");
        }
    }

    /**
     * Verify user's email address using the verification token.
     * @param token The email verification token.
     * @return A response entity with verification status.
     */

    @Transactional
    public RegistrationResponse verifyEmail(@NotBlank(message = "Token is required") String token) {
        try {
            // Hash the token to match stored hash
            String tokenHash = hashFormater.hashWithSHA256(token);

            // Find OTP log entry
            OtpEventLog otpLog = otpEventLogRepository.findAll().stream()
                    .filter(log -> log.getOtpType().equals("EMAIL_VERIFICATION"))
                    .filter(log -> !log.getVerified())
                    .filter(log -> log.getExpiresAt().isAfter(LocalDateTime.now()))
                    .filter(log -> log.getOtpCode().equals(tokenHash))
                    .findFirst()
                    .orElse(null);

            if (otpLog == null) {
                throw new BadRequestException("Invalid token or Cannot be empty");
            }

            // Get user
            AuthUserCredentials user = otpLog.getAuthUser();

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

            user.setUpdatedAt(LocalDateTime.now());
            userRepository.save(user);

            // Mark OTP as verified
            otpLog.setVerified(true);
            otpEventLogRepository.save(otpLog);

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
        } catch ( Exception e) {
            log.error("Error verifying email: {}", e.getMessage());
            throw new RuntimeException("Error verifying email. Please try again.");
        }
    }

    /**
     * Verify user's phone using the verification token.
     * @param token The email verification token.
     * @return A response entity with verification status.
     */

    @Transactional
    public RegistrationResponse verifyPhone(@NotBlank(message = "Token is required") String token, @NotBlank(message = "User ID is required") String userId) {
        try {

            UUID userUuid = UUID.fromString(userId);

            log.info(token, userUuid);

            // Find user
            AuthUserCredentials user = userRepository.findById(userUuid)
                    .orElseThrow(() -> new IllegalArgumentException("User not found"));

            // Find active phone verification OTP
            OtpEventLog otpLog = otpEventLogRepository.findAll().stream()
                    .filter(log -> log.getAuthUser().getAuthUserId().equals(userUuid))
                    .filter(log -> log.getOtpType().equals("PHONE_VERIFICATION"))
                    .filter(log -> !log.getVerified())
                    .filter(log -> log.getExpiresAt().isAfter(LocalDateTime.now()))
                    .findFirst()
                    .orElse(null);


            if (otpLog == null) {
                throw new BadRequestException("Invalid token or Cannot be empty");
            }

            // Verify OTP using bcrypt matching
            if (!passwordEncoder.matches(token, otpLog.getOtpCode())) {
                throw new BadRequestException("Invalid token or Cannot be empty");
            }

            // Update user verification status
            user.setPhoneVerified(true);

            // If user only has phone (not BOTH), activate account
            if (user.getLoginType() == AuthUserCredentials.LoginType.PHONE) {
                user.setStatus(AuthUserCredentials.Status.ACTIVE);
            }

        // If user has BOTH and email is already verified, activate account
        if (user.getLoginType() == AuthUserCredentials.LoginType.BOTH && user.isEmailVerified()) {
            user.setStatus(AuthUserCredentials.Status.ACTIVE);
        }

        user.setUpdatedAt(LocalDateTime.now());
        userRepository.save(user);

        // Mark OTP as verified
        otpLog.setVerified(true);
        otpEventLogRepository.save(otpLog);

        log.info("Phone verified successfully for user ID: {}", userUuid);

        return RegistrationResponse.builder()
                .success(true)
                .message("Phone verified successfully" +
                        (user.getStatus() == AuthUserCredentials.Status.ACTIVE
                                ? ". Your account is now active."
                                : ". Please verify your email if you haven't done yet, to activate your account to access full features."))
                .username(user.getUsername())
                .userId(user.getAuthUserId().toString())
                .build();

        } catch (IllegalArgumentException e) {
            log.error("Invalid user ID format: {}", e.getMessage());
            throw new IllegalArgumentException("Invalid user ID format. Please try again.");
        } catch (Exception e) {
            log.error("Error verifying phone: {}", e.getMessage());
            throw new RuntimeException("Error verifying phone. Please try again.");
        }
    }

    /**
     * Password reset for user using email or phone.
     * @param userContact The email or phone number verification token.
     * @return A response entity with verification status.
     */
    @Transactional
    public RegistrationResponse resetPassword(String userContact) {
        try {
            // Validate user contact (email or phone)
            AuthUserCredentials user = userRepository.findByEmailOrPhoneNumber(userContact, userContact)
                    .orElseThrow(() -> new RuntimeException("User not found"));

            // Generate reset token
            String resetToken = UUID.randomUUID().toString();

            // Save reset token with expiration
            PasswordResetToken passwordResetToken = new PasswordResetToken();
            passwordResetToken.setToken(resetToken);
            passwordResetToken.setUser(user);
            passwordResetToken.setExpiryDate(LocalDateTime.now().plusHours(1));
            passwordResetTokenRepository.save(passwordResetToken);

            // Send reset link/OTP based on contact type
            if (userContact.contains("@")) {
                // Email reset
                emailService.sendPasswordResetEmail(user.getEmail(), resetToken, user.getAuthUserId());
                return RegistrationResponse.builder()
                        .success(true)
                        .email(user.getEmail())
                        .message("Password reset link sent to email")
                        .build();
            } else {
                // Phone reset with OTP
                String otp = otpService.generatePasswordResetOtp(user.getAuthUserId());
                smsService.sendPasswordResetSms(user.getPhoneNumber(), otp, user.getAuthUserId());
                return RegistrationResponse.builder()
                        .success(true)
                        .message("Password reset OTP sent to phone")
                        .build();
            }

        } catch (Exception e) {
            log.error("Error in password reset: {}", e.getMessage());
            throw new RuntimeException("Error in password reset. Please try again.");
        }
    }

    /**
     * Conform password reset using token and new password.
     * @param token The email or phone number verification token.
     * @return A response entity with verification status.
     */
    @Transactional
    public RegistrationResponse confirmPasswordReset(String token, String newPassword) {
        try {
            PasswordResetToken resetToken = passwordResetTokenRepository.findByToken(token)
                    .orElseThrow(() -> new BadRequestException("Invalid reset token"));

            if (resetToken.isExpired()) {
                throw new BadRequestException("Invalid reset token");
            }

            AuthUserCredentials user = resetToken.getUser();
            user.setPasswordHash(passwordEncoder.encode(newPassword));
            user.setUpdatedAt(LocalDateTime.now());
            userRepository.save(user);

            passwordResetTokenRepository.delete(resetToken);

            return RegistrationResponse.builder()
                    .success(true)
                    .message("Password reset successfully")
                    .build();

        } catch (Exception e) {
            log.error("Error confirming password reset: {}", e.getMessage());
            throw new RuntimeException("Error confirming password reset. Please try again.");
        }
    }

}
