package ai.builderr.signalpost.controller;

import ai.builderr.signalpost.security.GuardRailController;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestTemplate;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.*;
import java.util.regex.Pattern;

@RestController
@RequestMapping("/api")
@CrossOrigin(origins = "*")
public class CompanyIntelligenceController {

    private final JdbcTemplate jdbcTemplate;
    private final RestTemplate restTemplate;
    private final GuardRailController guardRailController;

    private static final Pattern COMPANY_NUMBER_PATTERN = Pattern.compile("^\\d{9}$");

    public CompanyIntelligenceController(JdbcTemplate jdbcTemplate, RestTemplate restTemplate, GuardRailController guardRailController) {
        this.jdbcTemplate = jdbcTemplate;
        this.restTemplate = restTemplate;
        this.guardRailController = guardRailController;
    }

    @GetMapping("/companies")
    public ResponseEntity<List<Map<String, Object>>> getCompanies() {
        List<Map<String, Object>> companies = jdbcTemplate.queryForList("SELECT * FROM compiled_companies ORDER BY last_modified_timestamp DESC");
        for (Map<String, Object> company : companies) {
            String companyNumber = (String) company.get("company_number");
            List<Map<String, Object>> evidences = jdbcTemplate.queryForList("SELECT * FROM lineage_evidences WHERE company_number = ?", companyNumber);
            company.put("lineage_evidences", evidences);
        }
        return ResponseEntity.ok(companies);
    }

    @PostMapping("/companies/lookup/{companyNumber}")
    public ResponseEntity<?> lookupCompany(@PathVariable("companyNumber") String companyNumber) {
        if (companyNumber == null || !COMPANY_NUMBER_PATTERN.matcher(companyNumber).matches()) {
            return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(Map.of("error", "Invalid company number format. Must be exactly 9 digits."));
        }

        guardRailController.incrementNetworkCalls(1);

        String brregUrl = "https://" + "data.brreg.no/enhetsregisteret/api/enheter/" + companyNumber;
        Map<String, Object> brregData = null;
        try {
            brregData = restTemplate.getForObject(brregUrl, Map.class);
        } catch (Exception e) {
            // fallback or pass
        }

        String name = brregData != null && brregData.get("navn") != null ? brregData.get("navn").toString() : "Unknown Company";
        String foundOrgNum = brregData != null && brregData.get("organisasjonsnummer") != null ? brregData.get("organisasjonsnummer").toString() : companyNumber;
        String rawJson = brregData != null ? brregData.toString() : "{}";

        String hash = computeSha256(rawJson);

        jdbcTemplate.update(
            "INSERT INTO compiled_companies (company_number, company_name, delta_sync_hash, last_modified_timestamp) VALUES (?, ?, ?, ?) " +
            "ON CONFLICT (company_number) DO UPDATE SET company_name = EXCLUDED.company_name, delta_sync_hash = EXCLUDED.delta_sync_hash, last_modified_timestamp = EXCLUDED.last_modified_timestamp",
            foundOrgNum, name, hash, Instant.now().toString()
        );

        jdbcTemplate.update(
            "INSERT INTO lineage_evidences (company_number, evidence_source, payload_json, recorded_at) VALUES (?, ?, ?, ?)",
            foundOrgNum, "Brønnøysund Register API", rawJson, Instant.now().toString()
        );

        List<Map<String, Object>> evidences = jdbcTemplate.queryForList("SELECT * FROM lineage_evidences WHERE company_number = ?", foundOrgNum);
        Map<String, Object> result = new HashMap<>();
        result.put("company_number", foundOrgNum);
        result.put("company_name", name);
        result.put("delta_sync_hash", hash);
        result.put("lineage_evidences", evidences);

        return ResponseEntity.ok(result);
    }

    @PostMapping("/auth/signin")
    public ResponseEntity<Map<String, Object>> signin(@RequestBody(required = false) Map<String, Object> body) {
        return ResponseEntity.ok(Map.of("status", "authenticated", "session_token", UUID.randomUUID().toString(), "user", body != null ? body : Map.of()));
    }

    @PostMapping("/auth/signup")
    public ResponseEntity<Map<String, Object>> signup(@RequestBody(required = false) Map<String, Object> body) {
        return ResponseEntity.ok(Map.of("status", "created", "session_token", UUID.randomUUID().toString(), "user", body != null ? body : Map.of()));
    }

    @PostMapping("/auth/oauth")
    public ResponseEntity<Map<String, Object>> oauth(@RequestBody(required = false) Map<String, Object> body) {
        return ResponseEntity.ok(Map.of("status", "oauth_authenticated", "session_token", UUID.randomUUID().toString(), "user", body != null ? body : Map.of()));
    }

    @GetMapping("/metrics")
    public ResponseEntity<Map<String, Object>> getMetrics() {
        Integer companyCount = jdbcTemplate.queryForObject("SELECT COUNT(*) FROM compiled_companies", Integer.class);
        Integer evidenceCount = jdbcTemplate.queryForObject("SELECT COUNT(*) FROM lineage_evidences", Integer.class);

        Map<String, Object> metrics = new HashMap<>();
        metrics.put("compiled_companies_count", companyCount != null ? companyCount : 0);
        metrics.put("lineage_evidences_count", evidenceCount != null ? evidenceCount : 0);
        metrics.put("current_guardrail_calls", guardRailController.getCurrentCalls());
        metrics.put("max_guardrail_cap", guardRailController.getMaxCap());
        metrics.put("virtual_threads_active", Thread.currentThread().isVirtual());

        return ResponseEntity.ok(metrics);
    }

    private String computeSha256(String input) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] encodedhash = digest.digest(input.getBytes(StandardCharsets.UTF_8));
            StringBuilder hexString = new StringBuilder(2 * encodedhash.length);
            for (byte b : encodedhash) {
                String hex = Integer.toHexString(0xff & b);
                if (hex.length() == 1) hexString.append('0');
                hexString.append(hex);
            }
            return hexString.toString();
        } catch (NoSuchAlgorithmException e) {
            return "hash-error";
        }
    }
}
