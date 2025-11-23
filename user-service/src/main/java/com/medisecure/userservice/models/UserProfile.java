package com.medisecure.userservice.models;

import jakarta.persistence.*;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Past;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;

import java.time.LocalDate;
import java.time.LocalDateTime;


@Entity
@Table(name = "user_profiles")
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class UserProfile {

    private enum Gender {
        MALE,FEMALE,THIRD,OTHER
    }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long profileId;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "userId", nullable = false, unique = true)
    private User user;

    @Column(nullable = false)
    @Size(min = 1, max = 64, message = "First name must be between 1 and 64 characters")
    @NotBlank(message = "First name is required")
    private String firstName;

    private String MiddleName;

    @Column(nullable = false)
    @Size(min = 1, max = 64, message = "Last name must be between 1 and 64 characters")
    @NotBlank(message = "Last name is required")
    private String lastName;

    @Column(nullable = false)
    @Past(message = "Date of birth must be in the past")
    private LocalDate dob;

    @Enumerated(EnumType.STRING)
    @NotBlank(message = "Gender is required")
    @Pattern(regexp = "Male|Female|Thrid|Other", message = "Gender must be Male, Female, or Other")
    private Gender gender = Gender.OTHER;

    @Size(min = 10, max = 10, message = "Phone number must be 10 digits")
    private String phoneNumber;

    private String avatarUrl;

    @Size(max = 255)
    private String addressLine1;
    private String addressLine2;

    private String city;
    private String state;

    @Size(max = 12)
    private String zipCode;

    private String country;

    @Size(max = 10)
    private String emergencyContactName;

    @Size(max = 10)
    private String emergencyContactPhone;

    @Size(max = 20)
    private String insuranceProvider;
    private String insurancePolicyNo;
    private String insurancePhotoUrl;

    private String language;
    private String timezone;

    @Column(columnDefinition = "TEXT")
    private String preferencesJson;

    @CreatedDate
    @Column(nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @LastModifiedDate
    @Column(nullable = false)
    private LocalDateTime updatedAt;

}
