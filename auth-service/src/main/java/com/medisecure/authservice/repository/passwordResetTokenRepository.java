package com.medisecure.authservice.repository;

import com.medisecure.authservice.models.PasswordResetToken;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface PasswordResetTokenRepository extends JpaRepository<PasswordResetToken, UUID> {
    Optional<PasswordResetToken> findByToken(String token);

    long countByUser_AuthUserIdAndExpiryDateAfter(UUID userId, LocalDateTime expiryDate);

    @Modifying
    @Query("DELETE FROM PasswordResetToken p WHERE p.user.authUserId = :userId")
    void deleteAllByUser_AuthUserId(@Param("userId") UUID userId);
}

