export type Evidence = {
  evidence_id?: string
  company_number?: string
  target_metric_key?: string
  extracted_text_snippet?: string
  source_url_link?: string
  crawl_timestamp?: string
  recorded_at?: string
  explanation_chain?: string
  payload_json?: string
}

export type Company = {
  company_number: string
  official_legal_name?: string
  company_name?: string
  registered_address?: string
  incorporation_date?: string
  financial_revenue?: string
  net_profit?: string
  delta_sync_hash?: string
  last_modified_timestamp?: string
  lineage_evidences?: Evidence[]
  agent_crawl?: AgentCrawl
  organisasjonsform_kode?: string
  antall_ansatte?: number
  naeringskode_beskrivelse?: string
  source_url?: string
  revenue_nok?: number | null
  ebitda_nok?: number | null
  data_origin?: string
}

export type AgentCrawl = {
  company_number: string
  official_legal_name?: string
  registered_address?: string
  incorporation_date?: string
  financial_revenue?: string
  net_profit?: string
  delta_sync_hash?: string
  explainability_logs?: string[]
  lineage_evidences?: Evidence[]
}

export type Metrics = {
  compiled_companies_count: number
  lineage_evidences_count: number
  current_guardrail_calls: number
  max_guardrail_cap: number
  virtual_threads_active: boolean
}

export type ServiceState = 'checking' | 'online' | 'offline'