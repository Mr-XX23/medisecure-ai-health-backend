package com.medisecure.authservice.models;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Column;
import jakarta.persistence.Table;
import jakarta.persistence.Enumerated;
import jakarta.persistence.EnumType;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;

import java.time.LocalDateTime;
import java.util.UUID;

@Entity
@Table(name = "auth_user_credentials")
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class AuthUserCredentials {

    public enum LoginType {
        EMAIL,
        PHONE,
        THIRD_PARTY,
        BOTH
    }

    public enum Status {
        ACTIVE,
        INACTIVE,
        SUSPENDED,
        LOCKED
    }

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "auth_user_id", columnDefinition = "UUID", updatable = false, nullable = false)
    private UUID authUserId;

    @Column(unique = true, nullable = false, updatable = false, length = 20)
    @NotBlank( message = "Username is mandatory")
    private String username;

    @Email
    @Column(unique = true, length = 100)
    private String email;

    @Pattern(regexp = "^\\+?[1-9]\\d{1,14}$", message = "Invalid phone number format")
    @Column(unique = true, length = 20)
    private String phoneNumber;

    @Column(length = 256)
    private String passwordHash;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private LoginType loginType;

    @Enumerated(EnumType.STRING)
    @Column(length = 16)
    private Status status;

    @Column(nullable = false)
    private boolean isEmailVerified = false;

    @Column(nullable = false)
    private boolean isPhoneVerified = false;

    @Column(nullable = false)
    private boolean mfaEnabled = false;

    @CreatedDate
    private LocalDateTime createdAt;

    @LastModifiedDate
    private LocalDateTime updatedAt;

    private LocalDateTime lastLoginAt;
}
