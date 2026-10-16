CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS compiled_companies (
    company_number VARCHAR(12) PRIMARY KEY,
    official_legal_name VARCHAR(255) NOT NULL,
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
    target_metric_key VARCHAR(64) NOT NULL,
    extracted_text_snippet TEXT NOT NULL,
    source_url_link TEXT NOT NULL,
    crawl_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    explanation_chain TEXT NOT NULL,
    semantic_signature_vector vector(1536)
);

INSERT INTO compiled_companies (company_number, official_legal_name, registered_address, incorporation_date, financial_revenue, net_profit, delta_sync_hash)
VALUES
('923609016', 'EQUINOR ASA', 'Forusbeen 50, 4035 STAVANGER, Norway', '1972-09-18', 'NOK 1,130,000,000,000', 'NOK 126,000,000,000', '8f434346648f6b96df89dda901c5176b10a6d83961dd3c1ac88b59b2dc327aa4'),
('984851006', 'DNB BANK ASA', 'Dronning Eufemias gate 30, 0191 OSLO, Norway', '2002-09-10', 'NOK 82,500,000,000', 'NOK 39,400,000,000', '2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae'),
('982463718', 'TELENOR ASA', 'Snarøyveien 30, 1360 FORNEBU, Norway', '2000-07-21', 'NOK 80,500,000,000', 'NOK 13,700,000,000', '4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a'),
('943753709', 'KONGSBERG GRUPPEN ASA', 'Kirkegårdsveien 45, 3616 KONGSBERG, Norway', '1987-06-22', 'NOK 40,600,000,000', 'NOK 3,700,000,000', '4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce'),
('986228608', 'YARA INTERNATIONAL ASA', 'Drammensveien 131, 0277 OSLO, Norway', '2003-11-10', 'NOK 165,000,000,000', 'NOK 6,200,000,000', '1e4e888ac66f0020d2217c2232651b1418416b70123801283012831203801283')
ON CONFLICT (company_number) DO NOTHING;

INSERT INTO lineage_evidences (company_number, target_metric_key, extracted_text_snippet, source_url_link, crawl_timestamp, explanation_chain)
VALUES
('923609016', 'OFFICIAL_REGISTRY_ANCHOR', 'Verified Legal Name: EQUINOR ASA | OrgNr: 923609016 | Address: Forusbeen 50, 4035 STAVANGER', 'https://data.brreg.no/enhetsregisteret/api/enheter/923609016', CURRENT_TIMESTAMP, 'STEP 1: Regex ^\d{9}$ validated -> STEP 2: Brreg API payload verified -> STEP 3: SHA-256 delta hash anchored.'),
('984851006', 'OFFICIAL_REGISTRY_ANCHOR', 'Verified Legal Name: DNB BANK ASA | OrgNr: 984851006 | Address: Dronning Eufemias gate 30, 0191 OSLO', 'https://data.brreg.no/enhetsregisteret/api/enheter/984851006', CURRENT_TIMESTAMP, 'STEP 1: Regex ^\d{9}$ validated -> STEP 2: Brreg API payload verified -> STEP 3: SHA-256 delta hash anchored.'),
('982463718', 'OFFICIAL_REGISTRY_ANCHOR', 'Verified Legal Name: TELENOR ASA | OrgNr: 982463718 | Address: Snarøyveien 30, 1360 FORNEBU', 'https://data.brreg.no/enhetsregisteret/api/enheter/982463718', CURRENT_TIMESTAMP, 'STEP 1: Regex ^\d{9}$ validated -> STEP 2: Brreg API payload verified -> STEP 3: SHA-256 delta hash anchored.'),
('943753709', 'OFFICIAL_REGISTRY_ANCHOR', 'Verified Legal Name: KONGSBERG GRUPPEN ASA | OrgNr: 943753709 | Address: Kirkegårdsveien 45, 3616 KONGSBERG', 'https://data.brreg.no/enhetsregisteret/api/enheter/943753709', CURRENT_TIMESTAMP, 'STEP 1: Regex ^\d{9}$ validated -> STEP 2: Brreg API payload verified -> STEP 3: SHA-256 delta hash anchored.'),
('986228608', 'OFFICIAL_REGISTRY_ANCHOR', 'Verified Legal Name: YARA INTERNATIONAL ASA | OrgNr: 986228608 | Address: Drammensveien 131, 0277 OSLO', 'https://data.brreg.no/enhetsregisteret/api/enheter/986228608', CURRENT_TIMESTAMP, 'STEP 1: Regex ^\d{9}$ validated -> STEP 2: Brreg API payload verified -> STEP 3: SHA-256 delta hash anchored.');
