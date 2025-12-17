package com.medisecure.authservice.repository;

import com.medisecure.authservice.models.TokenStore;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface TokenStoreRepository extends JpaRepository<TokenStore, UUID> {

    Optional<TokenStore> findByTokenStringAndRevokedFalse(String refreshToken);

    List<TokenStore> findAllByAuthUser_AuthUserIdAndRevokedFalse(UUID userId);

    List<TokenStore> findAllByAuthUser_AuthUserIdAndTokenTypeAndRevokedFalse(UUID userId, String tokenType);

    void deleteByExpiresAtBefore(LocalDateTime dateTime);
}
