package ai.builderr.signalpost.controller;

import ai.builderr.signalpost.security.GuardRailController;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.RestTemplate;

import java.sql.Date;
import java.time.Instant;
import java.sql.Timestamp;
import java.time.format.DateTimeParseException;
import java.util.*;
import java.util.regex.Pattern;

@RestController
@RequestMapping("/api")
public class CompanyIntelligenceController {

    private final JdbcTemplate jdbcTemplate;
    private final RestTemplate restTemplate;
    private final GuardRailController guardRailController;
    private final String agentServiceUrl;

    private static final Pattern COMPANY_NUMBER_PATTERN = Pattern.compile("^\\d{9}$");

    public CompanyIntelligenceController(
        JdbcTemplate jdbcTemplate,
        RestTemplate restTemplate,
        GuardRailController guardRailController,
        @Value("${agent.service.url:http://localhost:8000}") String agentServiceUrl
    ) {
        this.jdbcTemplate = jdbcTemplate;
        this.restTemplate = restTemplate;
        this.guardRailController = guardRailController;
        this.agentServiceUrl = agentServiceUrl;
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

        Map<String, Object> agentData;
        try {
            agentData = restTemplate.postForObject(agentServiceUrl + "/api/v1/crawl/" + companyNumber, null, Map.class);
        } catch (HttpStatusCodeException e) {
            HttpStatus status = e.getStatusCode().is4xxClientError()
                ? HttpStatus.valueOf(e.getStatusCode().value())
                : HttpStatus.BAD_GATEWAY;
            return ResponseEntity.status(status)
                .body(Map.of("error", "Agent registry lookup failed. No company profile was stored."));
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                .body(Map.of("error", "Agent registry lookup failed. No company profile was stored."));
        }

        if (agentData == null || !companyNumber.equals(String.valueOf(agentData.get("company_number")))
            || agentData.get("official_legal_name") == null || agentData.get("official_legal_name").toString().isBlank()
            || agentData.get("delta_sync_hash") == null) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                .body(Map.of("error", "Agent returned an incomplete or mismatched company record. No profile was stored."));
        }

        String name = agentData.get("official_legal_name").toString();
        String foundOrgNum = companyNumber;
        String hash = agentData.get("delta_sync_hash").toString();
        if (!hash.matches("^[a-fA-F0-9]{64}$")) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                .body(Map.of("error", "Agent returned an invalid source hash. No profile was stored."));
        }
        Timestamp recordedAt = Timestamp.from(Instant.now());
        String registeredAddress = agentData.get("registered_address") instanceof String value ? value : null;
        Date incorporationDate = null;
        if (agentData.get("incorporation_date") instanceof String value && !value.isBlank()) {
            try {
                incorporationDate = Date.valueOf(value);
            } catch (IllegalArgumentException e) {
                return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                    .body(Map.of("error", "Agent returned an invalid incorporation date. No profile was stored."));
            }
        }

        String expectedSourceUrl = "https://data.brreg.no/enhetsregisteret/api/enheter/" + companyNumber;
        Object rawEvidence = agentData.get("lineage_evidences");
        List<Map<String, Object>> verifiedEvidence = new ArrayList<>();
        boolean hasLegalNameEvidence = false;
        if (rawEvidence instanceof List<?> evidenceList) {
            for (Object item : evidenceList) {
                if (!(item instanceof Map<?, ?> evidence)) continue;
                String targetMetric = evidence.get("target_metric_key") instanceof String value ? value : null;
                String snippet = evidence.get("extracted_text_snippet") instanceof String value ? value : null;
                String sourceUrl = evidence.get("source_url_link") instanceof String value ? value : null;
                String explanation = evidence.get("explanation_chain") instanceof String value ? value : "Read from the Brreg registry response.";
                if (targetMetric == null || snippet == null || sourceUrl == null || !expectedSourceUrl.equals(sourceUrl)) continue;
                if (!(evidence.get("crawl_timestamp") instanceof String timestamp)) continue;
                Timestamp crawlTimestamp;
                try {
                    crawlTimestamp = Timestamp.from(Instant.parse(timestamp));
                } catch (DateTimeParseException e) {
                    continue;
                }
                Map<String, Object> verified = new HashMap<>();
                verified.put("target_metric_key", targetMetric);
                verified.put("extracted_text_snippet", snippet);
                verified.put("source_url_link", sourceUrl);
                verified.put("crawl_timestamp", crawlTimestamp);
                verified.put("explanation_chain", explanation);
                verifiedEvidence.add(verified);
                hasLegalNameEvidence |= "official_legal_name".equals(targetMetric);
            }
        }
        if (!hasLegalNameEvidence) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                .body(Map.of("error", "Agent response lacked matching legal-name source evidence. No profile was stored."));
        }

        jdbcTemplate.update(
            "INSERT INTO compiled_companies (company_number, official_legal_name, registered_address, incorporation_date, financial_revenue, net_profit, delta_sync_hash, last_modified_timestamp) VALUES (?, ?, ?, ?, 'N/A', 'N/A', ?, ?) " +
            "ON CONFLICT (company_number) DO UPDATE SET official_legal_name = EXCLUDED.official_legal_name, registered_address = EXCLUDED.registered_address, incorporation_date = EXCLUDED.incorporation_date, financial_revenue = EXCLUDED.financial_revenue, net_profit = EXCLUDED.net_profit, delta_sync_hash = EXCLUDED.delta_sync_hash, last_modified_timestamp = EXCLUDED.last_modified_timestamp",
            foundOrgNum, name, registeredAddress, incorporationDate, hash, recordedAt
        );

        for (Map<String, Object> evidence : verifiedEvidence) {
            jdbcTemplate.update(
                "INSERT INTO lineage_evidences (company_number, target_metric_key, extracted_text_snippet, source_url_link, crawl_timestamp, explanation_chain) " +
                "SELECT ?, ?, ?, ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM lineage_evidences WHERE company_number = ? AND target_metric_key = ? AND extracted_text_snippet = ? AND source_url_link = ?)",
                foundOrgNum,
                evidence.get("target_metric_key"),
                evidence.get("extracted_text_snippet"),
                evidence.get("source_url_link"),
                evidence.get("crawl_timestamp"),
                evidence.get("explanation_chain"),
                foundOrgNum,
                evidence.get("target_metric_key"),
                evidence.get("extracted_text_snippet"),
                evidence.get("source_url_link")
            );
        }

        List<Map<String, Object>> evidences = jdbcTemplate.queryForList("SELECT * FROM lineage_evidences WHERE company_number = ?", foundOrgNum);
        Map<String, Object> result = new HashMap<>();
        result.put("company_number", foundOrgNum);
        result.put("official_legal_name", name);
        result.put("registered_address", registeredAddress);
        result.put("incorporation_date", incorporationDate);
        result.put("delta_sync_hash", hash);
        result.put("lineage_evidences", evidences);
        result.put("agent_crawl", agentData);

        return ResponseEntity.ok(result);
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

}
