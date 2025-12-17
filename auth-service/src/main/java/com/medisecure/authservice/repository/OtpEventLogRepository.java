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

    @Query("SELECT o FROM OtpEventLog o WHERE o.authUser.authUserId = :authUserId " +
            "AND o.otpType = :otpType AND o.verified = false " +
            "AND o.expiresAt > :now ORDER BY o.createdAt DESC")
    List<OtpEventLog> findActiveOtpsByUserAndType(
            @Param("authUserId") Long authUserId,
            @Param("otpType") String otpType,
            @Param("now") LocalDateTime now
    );

    @Query("SELECT o FROM OtpEventLog o WHERE o.authUser.authUserId = :authUserId " +
            "AND o.otpType = :otpType AND o.verified = false " +
            "AND o.expiresAt > :now ORDER BY o.createdAt DESC")
    Optional<OtpEventLog> findLatestActiveOtp(
            @Param("authUserId") Long authUserId,
            @Param("otpType") String otpType,
            @Param("now") LocalDateTime now
    );
}
