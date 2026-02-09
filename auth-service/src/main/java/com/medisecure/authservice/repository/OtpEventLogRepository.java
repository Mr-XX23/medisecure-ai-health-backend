package com.medisecure.authservice.repository;

import com.medisecure.authservice.models.OtpEventLog;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface OtpEventLogRepository extends JpaRepository<OtpEventLog, UUID> {

    Optional<OtpEventLog> findFirstByOtpTypeAndOtpCodeAndVerifiedAndExpiresAtAfter(
            String otpType,
            String otpCode,
            Boolean verified,
            LocalDateTime expiresAt
    );

    Optional<OtpEventLog> findFirstByAuthUser_AuthUserIdAndOtpTypeAndVerifiedFalseAndExpiresAtAfter(
            UUID authUserId,
            String otpType,
            LocalDateTime now
    );

    List<OtpEventLog> findAllByAuthUser_AuthUserIdAndOtpTypeAndVerifiedFalseAndExpiresAtAfter(
            UUID authUserId,
            String otpType,
            LocalDateTime expiresAt
    );
}
