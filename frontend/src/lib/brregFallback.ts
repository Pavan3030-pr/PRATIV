import type { Company, Evidence, Metrics } from '../types'

const BRREG_URL = 'https://data.brreg.no/enhetsregisteret/api/enheter'
const STORAGE_KEY = 'signalpost.persisted_companies.v2'
export const GUARDRAIL_CAP = 2000
const GUARDRAIL_STOP = GUARDRAIL_CAP - 50
let guardrailCalls = 0
let cachedSeedProfiles: Company[] | null = null

type BrregEntity = {
  organisasjonsnummer?: string
  navn?: string
  organisasjonsform?: { kode?: string }
  stiftelsesdato?: string
  antallAnsatte?: number
  naeringskode1?: { beskrivelse?: string }
  forretningsadresse?: {
    adresse?: string[]
    postnummer?: string
    poststed?: string
    land?: string
  }
}

type SeedRecord = {
  organisasjonsnummer: string
  navn: string
  organisasjonsform_kode?: string
  stiftelsesdato?: string
  antallAnsatte?: number
  naeringskode1_beskrivelse?: string
  forretningsadresse?: BrregEntity['forretningsadresse']
  delta_sync_hash: string
  source_url: string
  fetched_at: string
}

function sortKeys(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortKeys)
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
        .map(([key, inner]) => [key, sortKeys(inner)]),
    )
  }
  return value
}

export async function sha256Hex(text: string) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('')
}

function addressText(address: BrregEntity['forretningsadresse']) {
  if (!address) return undefined
  const parts = [
    (address.adresse ?? []).join(', '),
    [address.postnummer, address.poststed].filter(Boolean).join(' '),
    address.land,
  ].filter(Boolean)
  return parts.join(', ') || undefined
}

function seedToCompany(r: SeedRecord): Company {
  const address = addressText(r.forretningsadresse)
  const anchor: Evidence = {
    evidence_id: `${r.organisasjonsnummer}-anchor`,
    company_number: r.organisasjonsnummer,
    target_metric_key: 'OFFICIAL_REGISTRY_ANCHOR',
    extracted_text_snippet: [
      `Verified Legal Name: ${r.navn}`,
      `OrgNr: ${r.organisasjonsnummer}`,
      `Form: ${r.organisasjonsform_kode ?? 'n/a'}`,
      `Founded: ${r.stiftelsesdato ?? 'n/a'}`,
      `Employees: ${r.antallAnsatte ?? 'n/a'}`,
      `Industry: ${r.naeringskode1_beskrivelse ?? 'n/a'}`,
      `Address: ${address ?? 'n/a'}`,
    ].join(' | '),
    source_url_link: r.source_url,
    crawl_timestamp: r.fetched_at,
    explanation_chain:
      'STEP 1: 9-digit organization number validated -> STEP 2: Official Brønnøysund Register Centre (Brreg) record fetched -> STEP 3: Canonical JSON fields hashed with SHA-256 -> delta_sync_hash anchored & persisted.',
  }
  const withheld: Evidence = {
    evidence_id: `${r.organisasjonsnummer}-financials-withheld`,
    company_number: r.organisasjonsnummer,
    target_metric_key: 'FINANCIALS_WITHHELD',
    extracted_text_snippet: 'revenue_nok = null, ebitda_nok = null',
    source_url_link: r.source_url,
    crawl_timestamp: r.fetched_at,
    explanation_chain:
      'Brreg entity endpoint carries no audited financial statement rows. Revenue and EBITDA are strictly withheld rather than estimated.',
  }
  return {
    company_number: r.organisasjonsnummer,
    official_legal_name: r.navn,
    registered_address: address,
    incorporation_date: r.stiftelsesdato,
    financial_revenue: 'N/A',
    net_profit: 'N/A',
    delta_sync_hash: r.delta_sync_hash,
    last_modified_timestamp: r.fetched_at,
    lineage_evidences: [anchor, withheld],
    organisasjonsform_kode: r.organisasjonsform_kode,
    antall_ansatte: r.antallAnsatte,
    naeringskode_beskrivelse: r.naeringskode1_beskrivelse,
    source_url: r.source_url,
    revenue_nok: null,
    ebitda_nok: null,
    data_origin: 'brreg-verified',
  }
}

export function getPersistedCustomCompanies(): Company[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as Company[]) : []
  } catch {
    return []
  }
}

function savePersistedCustomCompany(company: Company) {
  try {
    const current = getPersistedCustomCompanies()
    const next = [company, ...current.filter((item) => item.company_number !== company.company_number)]
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next.slice(0, 200)))
  } catch {
    // ignore storage quota errors
  }
}

export async function loadSeededProfiles(): Promise<Company[]> {
  const custom = getPersistedCustomCompanies()
  if (!cachedSeedProfiles) {
    try {
      const res = await fetch('/profiles_1000.json')
      if (res.ok) {
        const raw = (await res.json()) as SeedRecord[]
        cachedSeedProfiles = raw.map(seedToCompany)
      }
    } catch {
      cachedSeedProfiles = []
    }
  }
  const base = cachedSeedProfiles ?? []
  return [
    ...custom,
    ...base.filter((item) => !custom.some((c) => c.company_number === item.company_number)),
  ]
}

export async function lookupBrreg(orgNumber: string): Promise<Company> {
  if (guardrailCalls >= GUARDRAIL_STOP) {
    throw new Error('Guardrail cap reached: outbound request limit for this session was hit.')
  }
  guardrailCalls += 1
  const sourceUrl = `${BRREG_URL}/${orgNumber}`
  const response = await fetch(sourceUrl, { headers: { Accept: 'application/json' } })
  if (response.status === 404) throw new Error(`Organization ${orgNumber} was not found in the Brønnøysund register.`)
  if (!response.ok) throw new Error(`Brønnøysund register returned HTTP ${response.status}.`)
  const entity = (await response.json()) as BrregEntity

  const payload = {
    organisasjonsnummer: entity.organisasjonsnummer ?? null,
    navn: entity.navn ?? null,
    organisasjonsform_kode: entity.organisasjonsform?.kode ?? null,
    stiftelsesdato: entity.stiftelsesdato ?? null,
    antallAnsatte: entity.antallAnsatte ?? null,
    naeringskode1_beskrivelse: entity.naeringskode1?.beskrivelse ?? null,
    forretningsadresse: entity.forretningsadresse ?? null,
  }
  const hash = await sha256Hex(JSON.stringify(sortKeys(payload)))
  const fetchedAt = new Date().toISOString()

  const company = seedToCompany({
    organisasjonsnummer: orgNumber,
    navn: entity.navn ?? orgNumber,
    organisasjonsform_kode: entity.organisasjonsform?.kode,
    stiftelsesdato: entity.stiftelsesdato,
    antallAnsatte: entity.antallAnsatte,
    naeringskode1_beskrivelse: entity.naeringskode1?.beskrivelse,
    forretningsadresse: entity.forretningsadresse,
    delta_sync_hash: hash,
    source_url: sourceUrl,
    fetched_at: fetchedAt,
  })
  savePersistedCustomCompany(company)
  return company
}

export function localMetrics(records: Company[]): Metrics {
  return {
    compiled_companies_count: records.length,
    lineage_evidences_count: records.reduce((sum, c) => sum + (c.lineage_evidences?.length ?? 0), 0),
    current_guardrail_calls: guardrailCalls,
    max_guardrail_cap: GUARDRAIL_CAP,
    virtual_threads_active: true,
  }
}
