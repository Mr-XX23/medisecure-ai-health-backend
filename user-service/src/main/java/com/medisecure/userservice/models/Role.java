package com.medisecure.userservice.models;

import jakarta.persistence.*;
import jakarta.validation.constraints.NotBlank;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "roles")
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Role {

    private enum RoleName {
        ADMIN, DOCTOR, NURSE, PATIENT, RECEPTIONIST
    }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long roleId;

    @Column(nullable = false, unique = true, length = 32)
    @Enumerated(EnumType.STRING)
    @NotBlank(message = "Role name is required")
    private RoleName roleName;

}
