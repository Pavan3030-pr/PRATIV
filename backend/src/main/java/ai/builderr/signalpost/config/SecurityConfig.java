package ai.builderr.signalpost.config;

import com.nimbusds.jose.jwk.source.ImmutableSecret;
import com.nimbusds.jose.proc.SecurityContext;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.web.util.UriComponentsBuilder;

import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;
import java.net.URI;
import java.time.Duration;
import java.time.Instant;
import java.util.Arrays;
import java.util.Base64;
import java.util.List;
import java.util.Locale;

@Configuration
public class SecurityConfig {

    @Bean
    SecretKey jwtSecretKey(@Value("${security.jwt.secret}") String encodedSecret) {
        byte[] secret;
        try {
            secret = Base64.getDecoder().decode(encodedSecret);
        } catch (IllegalArgumentException exception) {
            throw new IllegalStateException("JWT_SECRET must be a Base64-encoded secret.", exception);
        }
        if (secret.length < 32) {
            throw new IllegalStateException("JWT_SECRET must decode to at least 32 bytes for HS256.");
        }
        return new SecretKeySpec(secret, "HmacSHA256");
    }

    @Bean
    JwtEncoder jwtEncoder(SecretKey jwtSecretKey) {
        return new NimbusJwtEncoder(new ImmutableSecret<SecurityContext>(jwtSecretKey));
    }

    @Bean
    JwtDecoder jwtDecoder(
        SecretKey jwtSecretKey,
        @Value("${security.jwt.issuer}") String issuer,
        @Value("${security.jwt.audience}") String audience
    ) {
        NimbusJwtDecoder decoder = NimbusJwtDecoder.withSecretKey(jwtSecretKey)
            .macAlgorithm(MacAlgorithm.HS256)
            .build();
        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> jwt.getAudience().contains(audience)
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(new OAuth2Error("invalid_token", "Invalid JWT audience.", null));
        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            org.springframework.security.oauth2.jwt.JwtValidators.createDefaultWithIssuer(issuer),
            audienceValidator
        ));
        return decoder;
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource(
        @Value("${security.cors.allowed-origins}") String allowedOrigins
    ) {
        List<String> origins = Arrays.stream(allowedOrigins.split(","))
            .map(String::trim)
            .filter(origin -> !origin.isEmpty())
            .map(SecurityConfig::normalizeOrigin)
            .distinct()
            .toList();
        if (origins.isEmpty() || origins.contains("*")) {
            throw new IllegalStateException("FRONTEND_ORIGINS must contain explicit trusted frontend origins.");
        }
        CorsConfiguration configuration = new CorsConfiguration();
        configuration.setAllowedOrigins(origins);
        configuration.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
        configuration.setAllowedHeaders(List.of("Authorization", "Content-Type", "Accept"));
        configuration.setAllowCredentials(false);
        configuration.setMaxAge(3600L);
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", configuration);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        JwtEncoder jwtEncoder,
        @Value("${security.jwt.issuer}") String issuer,
        @Value("${security.jwt.audience}") String audience,
        @Value("${security.jwt.lifetime}") Duration lifetime,
        @Value("${security.frontend-url}") String frontendUrl,
        @Value("${security.cors.allowed-origins}") String allowedOrigins
    ) throws Exception {
        if (lifetime.isZero() || lifetime.isNegative() || lifetime.compareTo(Duration.ofHours(1)) > 0) {
            throw new IllegalStateException("JWT_LIFETIME must be positive and no longer than one hour.");
        }
        String trustedFrontendUrl = normalizeOrigin(frontendUrl);
        List<String> trustedOrigins = Arrays.stream(allowedOrigins.split(","))
            .map(String::trim)
            .filter(origin -> !origin.isEmpty())
            .map(SecurityConfig::normalizeOrigin)
            .toList();
        if (!trustedOrigins.contains(trustedFrontendUrl)) {
            throw new IllegalStateException("APP_FRONTEND_URL must also be listed in FRONTEND_ORIGINS.");
        }
        AuthenticationSuccessHandler successHandler = (request, response, authentication) -> {
            if (!(authentication instanceof org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken oauth)) {
                throw new OAuth2AuthenticationException("Unsupported OAuth authentication principal.");
            }

            OAuth2User user = oauth.getPrincipal();
            Instant issuedAt = Instant.now();
            JwtClaimsSet.Builder claims = JwtClaimsSet.builder()
                .issuer(issuer)
                .audience(List.of(audience))
                .issuedAt(issuedAt)
                .expiresAt(issuedAt.plus(lifetime))
                .subject(oauth.getAuthorizedClientRegistrationId() + ":" + oauth.getName())
                .claim("provider", oauth.getAuthorizedClientRegistrationId())
                .claim("name", userDisplayName(user, oauth.getName()));
            Object email = user.getAttributes().get("email");
            if (email instanceof String value && !value.isBlank()) {
                claims.claim("email", value);
            }
            JwsHeader header = JwsHeader.with(MacAlgorithm.HS256).build();
            String token = jwtEncoder.encode(JwtEncoderParameters.from(header, claims.build())).getTokenValue();
            URI destination = UriComponentsBuilder.fromUriString(trustedFrontendUrl)
                .fragment("access_token=" + token)
                .build()
                .toUri();
            response.sendRedirect(destination.toString());
        };

        AuthenticationFailureHandler failureHandler = (request, response, exception) -> {
            URI destination = UriComponentsBuilder.fromUriString(trustedFrontendUrl)
                .replaceQueryParam("auth_error", "oauth_failed")
                .fragment(null)
                .build()
                .toUri();
            response.setStatus(HttpStatus.FOUND.value());
            response.setHeader("Location", destination.toString());
        };

        http
            .cors(Customizer.withDefaults())
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .securityContext(context -> context.securityContextRepository(new RequestAttributeSecurityContextRepository()))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/oauth2/**", "/login/oauth2/**", "/error").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll()
            )
            .oauth2Login(oauth -> oauth
                .successHandler(successHandler)
                .failureHandler(failureHandler)
            )
            .oauth2ResourceServer(resourceServer -> resourceServer.jwt(Customizer.withDefaults()));
        return http.build();
    }

    private static String userDisplayName(OAuth2User user, String fallback) {
        for (String attribute : List.of("name", "login", "given_name")) {
            Object value = user.getAttributes().get(attribute);
            if (value instanceof String name && !name.isBlank()) {
                return name;
            }
        }
        return fallback;
    }

    private static String normalizeOrigin(String value) {
        URI uri;
        try {
            uri = URI.create(value);
        } catch (IllegalArgumentException exception) {
            throw new IllegalStateException("OAuth frontend and CORS origins must be valid origins.", exception);
        }
        String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);
        String host = uri.getHost() == null ? "" : uri.getHost().toLowerCase(Locale.ROOT);
        if ((!scheme.equals("http") && !scheme.equals("https"))
            || host.isBlank()
            || uri.getRawUserInfo() != null
            || (uri.getRawPath() != null && !uri.getRawPath().isEmpty() && !uri.getRawPath().equals("/"))
            || uri.getRawQuery() != null
            || uri.getRawFragment() != null) {
            throw new IllegalStateException("OAuth frontend and CORS settings must use origins without paths or credentials.");
        }
        if (scheme.equals("http") && !List.of("localhost", "127.0.0.1", "::1").contains(host)) {
            throw new IllegalStateException("Non-local OAuth frontend origins must use HTTPS.");
        }
        int port = uri.getPort();
        if ((scheme.equals("http") && port == 80) || (scheme.equals("https") && port == 443)) {
            port = -1;
        }
        try {
            return new URI(scheme, null, host, port, null, null, null).toString();
        } catch (java.net.URISyntaxException exception) {
            throw new IllegalStateException("OAuth frontend and CORS origins must be valid origins.", exception);
        }
    }
}
