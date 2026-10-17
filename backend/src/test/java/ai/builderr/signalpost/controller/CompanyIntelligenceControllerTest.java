package ai.builderr.signalpost.controller;

import ai.builderr.signalpost.security.GuardRailController;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.client.RestTemplate;

import java.util.Map;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.contains;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(MockitoExtension.class)
class CompanyIntelligenceControllerTest {

    @Mock
    private JdbcTemplate jdbcTemplate;

    @Mock
    private RestTemplate restTemplate;

    @Mock
    private GuardRailController guardRailController;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        CompanyIntelligenceController controller = new CompanyIntelligenceController(
            jdbcTemplate, restTemplate, guardRailController, "http://agent.test"
        );
        mockMvc = MockMvcBuilders.standaloneSetup(controller).build();
    }

    @Test
    void demoSessionRouteIsNotExposed() throws Exception {
        mockMvc.perform(post("/api/auth/session").contentType("application/json").content("{}"))
            .andExpect(status().isNotFound());
    }

    @Test
    void rejectsInvalidCompanyNumberWithoutCallingServices() throws Exception {
        mockMvc.perform(post("/api/companies/lookup/not-a-number"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error").value("Invalid company number format. Must be exactly 9 digits."));

        verifyNoInteractions(jdbcTemplate, restTemplate, guardRailController);
    }

    @Test
    void lookupPersistsUsingInitializedDatabaseColumns() throws Exception {
        when(restTemplate.postForObject(anyString(), eq(null), eq(Map.class)))
            .thenReturn(Map.of(
                "company_number", "984851006",
                "official_legal_name", "DNB BANK ASA",
                "registered_address", "Dronning Eufemias gate 12, 0191 OSLO",
                "incorporation_date", "2002-09-10",
                "delta_sync_hash", "a".repeat(64),
                "lineage_evidences", java.util.List.of(Map.of(
                    "target_metric_key", "official_legal_name",
                    "extracted_text_snippet", "Legal name 'DNB BANK ASA' returned by Brreg.",
                    "source_url_link", "https://data.brreg.no/enhetsregisteret/api/enheter/984851006",
                    "crawl_timestamp", "2026-10-16T14:19:00Z",
                    "explanation_chain", "Read from official Brreg response."
                ))
            ));

        mockMvc.perform(post("/api/companies/lookup/984851006"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.company_number").value("984851006"))
            .andExpect(jsonPath("$.official_legal_name").value("DNB BANK ASA"))
            .andExpect(jsonPath("$.delta_sync_hash").isNotEmpty());

        verify(jdbcTemplate).update(contains("financial_revenue, net_profit"), eq("984851006"), eq("DNB BANK ASA"), eq("Dronning Eufemias gate 12, 0191 OSLO"), any(), eq("a".repeat(64)), any());
        verify(jdbcTemplate).update(contains("target_metric_key"), eq("984851006"), eq("official_legal_name"), anyString(), anyString(), any(), anyString(), eq("984851006"), eq("official_legal_name"), anyString(), anyString());
    }

    @Test
    void registryFailureDoesNotPersistUnknownCompany() throws Exception {
        when(restTemplate.postForObject(anyString(), eq(null), eq(Map.class)))
            .thenThrow(new IllegalStateException("registry unavailable"));

        mockMvc.perform(post("/api/companies/lookup/984851006"))
            .andExpect(status().isBadGateway())
            .andExpect(jsonPath("$.error").value("Agent registry lookup failed. No company profile was stored."));

        verifyNoInteractions(jdbcTemplate);
    }

    @Test
    void mismatchedRegistryCompanyNumberIsNotPersisted() throws Exception {
        when(restTemplate.postForObject(anyString(), eq(null), eq(Map.class)))
            .thenReturn(Map.of("company_number", "923609016", "official_legal_name", "EQUINOR ASA", "delta_sync_hash", "b".repeat(64)));

        mockMvc.perform(post("/api/companies/lookup/984851006"))
            .andExpect(status().isBadGateway())
            .andExpect(jsonPath("$.error").value("Agent returned an incomplete or mismatched company record. No profile was stored."));

        verifyNoInteractions(jdbcTemplate);
    }

    @Test
    void responseWithoutMatchingSourceEvidenceIsNotPersisted() throws Exception {
        when(restTemplate.postForObject(anyString(), eq(null), eq(Map.class)))
            .thenReturn(Map.of(
                "company_number", "984851006",
                "official_legal_name", "DNB BANK ASA",
                "delta_sync_hash", "c".repeat(64),
                "lineage_evidences", java.util.List.of(Map.of(
                    "target_metric_key", "financial_revenue",
                    "extracted_text_snippet", "NOK 1,000,000",
                    "source_url_link", "https://example.invalid/fabricated",
                    "crawl_timestamp", "2026-10-16T14:19:00Z"
                ))
            ));

        mockMvc.perform(post("/api/companies/lookup/984851006"))
            .andExpect(status().isBadGateway())
            .andExpect(jsonPath("$.error").value("Agent response lacked matching legal-name source evidence. No profile was stored."));

        verifyNoInteractions(jdbcTemplate);
    }
}