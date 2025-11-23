package com.medisecure.userservice.models;

import jakarta.persistence.*;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Entity
@Table(name = "consents")
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Consent {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long consentId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "userId", nullable = false)
    private User user;

    @Column(nullable = false, length = 32)
    private String consentType;

    @Column(nullable = false)
    private Boolean accepted;

    @Column(nullable = false)
    private LocalDateTime acceptedAt;

    @Column(length = 16)
    private String version;
}
