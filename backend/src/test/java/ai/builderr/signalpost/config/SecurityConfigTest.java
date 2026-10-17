package ai.builderr.signalpost.config;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;

import java.time.Instant;
import java.util.Base64;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class SecurityConfigTest {

    private final SecurityConfig securityConfig = new SecurityConfig();

    @Test
    void requiresStrongBase64JwtSecret() {
        assertThrows(IllegalStateException.class, () -> securityConfig.jwtSecretKey("not-base64"));
        assertThrows(IllegalStateException.class, () ->
            securityConfig.jwtSecretKey(Base64.getEncoder().encodeToString(new byte[31]))
        );
    }

    @Test
    void jwtDecoderRequiresExpectedIssuerAndAudience() {
        var key = securityConfig.jwtSecretKey(Base64.getEncoder().encodeToString(new byte[32]));
        var encoder = securityConfig.jwtEncoder(key);
        var decoder = securityConfig.jwtDecoder(key, "test-issuer", "prativ-api");
        JwsHeader header = JwsHeader.with(MacAlgorithm.HS256).build();
        Instant issuedAt = Instant.now();
        JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer("test-issuer")
            .audience(List.of("prativ-api"))
            .subject("github:test-user")
            .issuedAt(issuedAt)
            .expiresAt(issuedAt.plusSeconds(60))
            .build();

        var decoded = decoder.decode(encoder.encode(JwtEncoderParameters.from(header, claims)).getTokenValue());
        assertEquals("github:test-user", decoded.getSubject());
        assertEquals("prativ-api", decoded.getAudience().getFirst());

        JwtClaimsSet wrongAudience = JwtClaimsSet.builder()
            .issuer("test-issuer")
            .audience(List.of("other-api"))
            .subject("github:test-user")
            .issuedAt(issuedAt)
            .expiresAt(issuedAt.plusSeconds(60))
            .build();
        String tokenWithWrongAudience = encoder.encode(JwtEncoderParameters.from(header, wrongAudience)).getTokenValue();
        assertThrows(BadJwtException.class, () -> decoder.decode(tokenWithWrongAudience));
    }
}
