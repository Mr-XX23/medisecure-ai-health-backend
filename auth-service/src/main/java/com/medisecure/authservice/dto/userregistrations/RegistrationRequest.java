package com.medisecure.authservice.dto.userregistrations;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class RegistrationRequest {

    @Size(min = 3, max = 24, message = "Username must be between 3 and 50 characters")
    private String username;

    @Email(message = "Email should be valid")
    private String email;

    @Pattern(regexp = "^\\+?[1-9]\\d{1,16}$", message = "Phone format is invalid")
    private String phoneNumber;

    @Size(min = 8, message = "Password must be at least 8 characters", max = 256)
    private String password;

}
