package com.reqvalidator.backend.controller;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.reqvalidator.backend.dto.UserResponse;
import com.reqvalidator.backend.model.User;
import com.reqvalidator.backend.repository.UserRepository;
import com.reqvalidator.backend.security.JwtService;

@RestController
@RequestMapping("/api/auth")
@CrossOrigin(origins = {
    "http://localhost:5173",
    "https://ai-software-requirement-validator.vercel.app"
})
public class AuthController {

    private static final Logger log =
            LoggerFactory.getLogger(AuthController.class);

    private final UserRepository userRepository;
    private final BCryptPasswordEncoder passwordEncoder;
    private final JwtService jwtService;

    public AuthController(
            UserRepository userRepository,
            JwtService jwtService) {
        this.userRepository = userRepository;
        this.jwtService = jwtService;
        this.passwordEncoder = new BCryptPasswordEncoder();
    }

    @PostMapping("/register")
    public ResponseEntity<?> register(@RequestBody User user) {
        if (user == null
                || user.getName() == null
                || user.getName().trim().isEmpty()) {
            return ResponseEntity.badRequest().body("Name is required.");
        }

        if (user.getEmail() == null
                || user.getEmail().trim().isEmpty()) {
            return ResponseEntity.badRequest().body("Email is required.");
        }

        if (user.getPassword() == null
                || user.getPassword().isEmpty()) {
            return ResponseEntity.badRequest().body("Password is required.");
        }

        String email = user.getEmail().trim().toLowerCase();
        user.setEmail(email);
        user.setName(user.getName().trim());

        try {
            List<User> existingUsers = userRepository.findAllByEmailIgnoreCase(email);
            if (!existingUsers.isEmpty()) {
                return ResponseEntity.status(HttpStatus.CONFLICT)
                        .body("An account with this email already exists. Please log in.");
            }

            user.setPassword(passwordEncoder.encode(user.getPassword()));
            User savedUser = userRepository.save(user);

            UserResponse response = new UserResponse(
                    savedUser.getId(),
                    savedUser.getName(),
                    savedUser.getEmail()
            );

            log.info("User registration completed successfully.");
            return ResponseEntity.status(HttpStatus.CREATED).body(response);
        } catch (Exception ex) {
            log.error("Registration failed while processing the user account.", ex);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(Map.of(
                            "error", "Registration failed",
                            "message", "The server could not complete registration. Check backend logs."
                    ));
        }
    }

    @PostMapping("/login")
    public ResponseEntity<?> login(@RequestBody User loginUser) {
        if (loginUser == null
                || loginUser.getEmail() == null
                || loginUser.getEmail().trim().isEmpty()) {
            return ResponseEntity.badRequest().body("Email is required.");
        }

        if (loginUser.getPassword() == null
                || loginUser.getPassword().isEmpty()) {
            return ResponseEntity.badRequest().body("Password is required.");
        }

        String email = loginUser.getEmail().trim().toLowerCase();

        try {
            log.info("Login request received.");

            List<User> matchingUsers = userRepository.findAllByEmailIgnoreCase(email);
            if (matchingUsers.isEmpty()) {
                log.info("Login rejected: account was not found.");
                return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                        .body("Invalid email or password.");
            }

            // Older deployments may already contain duplicate email records.
            // Match the supplied password against each record instead of
            // requiring MongoDB to return exactly one document.
            User user = matchingUsers.stream()
                    .filter(candidate -> candidate.getPassword() != null
                            && passwordEncoder.matches(
                                    loginUser.getPassword(),
                                    candidate.getPassword()))
                    .findFirst()
                    .orElse(null);

            if (user == null) {
                log.info("Login rejected: password did not match any account record.");
                return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                        .body("Invalid email or password.");
            }

            if (matchingUsers.size() > 1) {
                log.warn("Multiple user records share an email address; login matched one existing record. Duplicate records should be cleaned up.");
            }

            String token = jwtService.generateToken(user.getEmail());

            UserResponse userResponse = new UserResponse(
                    user.getId(),
                    user.getName(),
                    user.getEmail()
            );

            Map<String, Object> response = new HashMap<>();
            response.put("message", "Login successful");
            response.put("token", token);
            response.put("user", userResponse);

            log.info("Login completed successfully; authentication token generated.");
            return ResponseEntity.ok(response);
        } catch (Exception ex) {
            log.error("Login failed while looking up the account, verifying credentials, or generating the token.", ex);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(Map.of(
                            "error", "Login failed",
                            "message", "The server could not complete login. Check backend logs."
                    ));
        }
    }
}
