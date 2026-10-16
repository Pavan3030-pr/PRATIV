CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS compiled_companies (
    company_number VARCHAR(12) PRIMARY KEY,
    company_name VARCHAR(255) NOT NULL,
    official_legal_name VARCHAR(255),
    registered_address TEXT,
    incorporation_date DATE,
    financial_revenue VARCHAR(64) DEFAULT 'N/A',
    net_profit VARCHAR(64) DEFAULT 'N/A',
    delta_sync_hash VARCHAR(128) NOT NULL,
    last_modified_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lineage_evidences (
    evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_number VARCHAR(12) REFERENCES compiled_companies(company_number) ON DELETE CASCADE,
    evidence_source VARCHAR(256),
    payload_json TEXT,
    recorded_at TIMESTAMP WITH TIME ZONE,

    -- legacy / additional fields kept for compatibility
    target_metric_key VARCHAR(64),
    extracted_text_snippet TEXT,
    source_url_link TEXT,
    crawl_timestamp TIMESTAMP WITH TIME ZONE,
    explanation_chain TEXT,
    semantic_signature_vector vector(1536)
);

-- seed some initial companies (will not duplicate due to ON CONFLICT)
INSERT INTO compiled_companies (company_number, company_name, official_legal_name, registered_address, incorporation_date, financial_revenue, net_profit, delta_sync_hash)
VALUES
('923609016', 'EQUINOR ASA', 'EQUINOR ASA', 'Forusbeen 50, 4035 STAVANGER, Norway', '1972-09-18', 'NOK 1,130,000,000,000', 'NOK 126,000,000,000', 'seed-hash-1'),
('984851006', 'DNB BANK ASA', 'DNB BANK ASA', 'Dronning Eufemias gate 30, 0191 OSLO, Norway', '2002-09-10', 'NOK 82,500,000,000', 'NOK 39,400,000,000', 'seed-hash-2')
ON CONFLICT (company_number) DO NOTHING;

INSERT INTO lineage_evidences (company_number, evidence_source, payload_json, recorded_at, target_metric_key, extracted_text_snippet, source_url_link, crawl_timestamp, explanation_chain)
VALUES
('923609016', 'Seed Data', '{"note":"seed evidence for equinor"}', now(), 'OFFICIAL_REGISTRY_ANCHOR', 'Verified Legal Name: EQUINOR ASA', 'https://example.com/equinor', now(), 'seed'),
('984851006', 'Seed Data', '{"note":"seed evidence for dnb"}', now(), 'OFFICIAL_REGISTRY_ANCHOR', 'Verified Legal Name: DNB BANK ASA', 'https://example.com/dnb', now(), 'seed')
ON CONFLICT (evidence_id) DO NOTHING;
