package ai.builderr.signalpost.controller;

import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Map;

@RestController
@RequestMapping("/api/auth")
public class AuthenticationController {

    @GetMapping("/me")
    public Map<String, Object> currentUser(@AuthenticationPrincipal Jwt jwt) {
        Map<String, Object> user = new LinkedHashMap<>();
        user.put("name", jwt.getClaimAsString("name"));
        user.put("provider", jwt.getClaimAsString("provider"));
        String email = jwt.getClaimAsString("email");
        if (email != null) {
            user.put("email", email);
        }
        return Map.of("status", "authenticated", "user", user);
    }
}
