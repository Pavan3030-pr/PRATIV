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
  content_hash?: string
  website?: WebsiteCheck
  social_links?: SocialLink[]
  news?: NewsItem[]
  financials?: Financials | null
  missing_fields?: Record<string, string>
}

export type WebsiteCheck = {
  registry_url?: string | null
  url?: string | null
  status: string
  verified: boolean
  verified_by?: string | null
  verified_on?: string
  reason?: string
}

export type SocialLink = { platform: string; url: string; handle: string; found_on?: string; matched?: string }

export type NewsItem = { title: string; url: string; published_at: string; source?: string }

export type FinancialYear = {
  period_start?: string | null
  period_end: string
  currency: string
  account_type?: string
  revenue: number | null
  operating_result: number | null
  net_result: number | null
}

export type Financials = {
  period_start?: string | null
  period_end?: string | null
  currency?: string
  account_type?: string
  source_url?: string
  history?: FinancialYear[]
}

export type Metrics = {
  compiled_companies_count: number
  lineage_evidences_count: number
  current_guardrail_calls: number
  max_guardrail_cap: number
  virtual_threads_active: boolean
}

export type ServiceState = 'checking' | 'online' | 'offline'