import { sha256Hex } from './brregFallback'

export type ExFact = {
  k: string
  l: string
  v: string
  t: string
  p: string
  s: string
  e: string
  u?: string
}

export type ExDoc = {
  n: string
  name: string
  base: string
  summary: string
  hash: string
  content_hash: string
  update: { status: string; changed: string[] }
  missing: Record<string, string>
  /** True when this record was read live from Brreg and the agent has not enriched it yet. */
  registryOnly?: boolean
  facts: ExFact[]
  fin: {
    period_start?: string | null
    period_end?: string | null
    currency?: string | null
    account_type?: string | null
    source_url?: string | null
    revenue?: number | null
    operating_result?: number | null
    net_result?: number | null
  } | null
  web: { url?: string | null; verified: boolean; by?: string | null } | null
  news: { title: string; url: string; at: string }[]
  jobs: { title: string; url: string; at?: string | null }[]
  social: { platform: string; url: string }[]
}

/** [orgnr, name, city, form, industry, hasAccounts, hasWebsite] */
export type IndexRow = [string, string, string, string, string, number, number]

export type CheckResult = { tone: 'ok' | 'warn' | 'info'; text: string }

let indexPromise: Promise<IndexRow[]> | null = null
const docs = new Map<string, Promise<ExDoc>>()
const live = new Map<string, Promise<unknown>>()

export function loadIndex() {
  if (!indexPromise) {
    indexPromise = fetch('/explore/index.json')
      .then((r) => {
        if (!r.ok) throw new Error('Company index unavailable')
        return r.json() as Promise<IndexRow[]>
      })
      // A transient failure must not poison the cache: the next attempt tries again.
      .catch((error: unknown) => {
        indexPromise = null
        throw error
      })
  }
  return indexPromise
}

export function loadDoc(org: string) {
  let p = docs.get(org)
  if (!p) {
    p = fetch(`/explore/c/${org}.json`).then((r) => {
      // A single-page host answers a missing file with the app's HTML and a 200, so the status alone
      // cannot be trusted: a non-JSON body means this company has no crawled profile.
      const type = r.headers.get('content-type') ?? ''
      if (!r.ok || !type.includes('json')) throw new Error('Company not found in this dataset')
      return r.json() as Promise<ExDoc>
    })
    p.catch(() => docs.delete(org))
    docs.set(org, p)
  }
  return p
}

export function sourceLabel(url: string) {
  if (url.includes('/regnskapsregisteret/')) return 'Regnskapsregisteret (annual accounts)'
  if (url.includes('/roller')) return 'Enhetsregisteret roles'
  if (url.includes('/underenheter')) return 'Enhetsregisteret sub-units'
  if (url.includes('/enhetsregisteret/')) return 'Enhetsregisteret'
  try {
    return new URL(url).hostname
  } catch {
    return 'Source'
  }
}

function fetchLive(url: string) {
  let p = live.get(url)
  if (!p) {
    p = fetch(url, { headers: { Accept: 'application/json' } }).then(async (r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      return r.json() as Promise<unknown>
    })
    p.catch(() => live.delete(url))
    live.set(url, p)
  }
  return p
}

// Field paths look like `navn` or `naeringskode1.beskrivelse`; anything computed from several fields has no simple path.
const simplePath = /^[A-Za-z][A-Za-z0-9]*(\.[A-Za-z][A-Za-z0-9]*)*$/

function readPath(record: Record<string, unknown>, path: string): unknown {
  return path.split('.').reduce<unknown>((acc, key) => {
    if (!acc || typeof acc !== 'object') return undefined
    return (acc as Record<string, unknown>)[key]
  }, record)
}

/** Re-fetch the fact's own source and compare it with what was stored. Never claims more than it checked. */
export async function checkFact(fact: ExFact, base: string): Promise<CheckResult> {
  const url = fact.u ?? base
  if (!url.startsWith('https://data.brreg.no/')) {
    return { tone: 'info', text: 'This fact comes from the company’s own website. Open the source to check it there.' }
  }
  let data: unknown
  try {
    data = await fetchLive(url)
  } catch {
    return { tone: 'info', text: 'Could not reach the source from this browser. Use “Open source” to check it directly.' }
  }
  const record = data as Record<string, unknown>
  const raw = simplePath.test(fact.p) ? readPath(record, fact.p) : undefined
  if (typeof raw === 'string' || typeof raw === 'number' || typeof raw === 'boolean') {
    const live = typeof raw === 'string' ? raw.trim() : raw
    const shown = typeof live === 'boolean' ? (live ? 'Yes' : 'No') : String(live)
    if (fact.s && (await sha256Hex(JSON.stringify(live))) === fact.s) {
      return { tone: 'ok', text: 'Verified: the live source still produces the stored SHA-256.' }
    }
    if (shown === fact.v) return { tone: 'ok', text: 'Verified: the live source shows the same value.' }
    return { tone: 'warn', text: `Source now shows “${shown}” — the stored value may be out of date.` }
  }
  return {
    tone: 'info',
    text: 'Source reachable. This fact is derived from several fields, so open the source to inspect it.',
  }
}

const CSV_FIELDS = ['field', 'label', 'value', 'source_url', 'source_field', 'retrieved_at', 'value_sha256', 'explanation'] as const

function csvCell(value: string) {
  return /[",\n]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value
}

/** Every published fact with its source, as a spreadsheet a reviewer can audit offline. */
export function factsCsv(doc: ExDoc): string {
  const rows = [CSV_FIELDS.join(',')]
  for (const fact of doc.facts) {
    rows.push(
      [fact.k, fact.l, fact.v, fact.u ?? doc.base, fact.p, fact.t, fact.s, fact.e].map((cell) => csvCell(cell ?? '')).join(','),
    )
  }
  return `${rows.join('\n')}\n`
}

export function downloadText(fileName: string, text: string, mime: string) {
  const url = URL.createObjectURL(new Blob([text], { type: mime }))
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.append(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

// --------------------------------------------------------------------------- live registry lookup
// The committed dataset is a crawl of a seeded company list, so a search for a company outside it used to
// end in "not found" even though the register has it. The register API is public, CORS-enabled and is the
// same source the agent reads, so a miss now falls back to it and shows a clearly labelled registry-only
// record instead of pretending the company does not exist.

const BRREG = 'https://data.brreg.no/enhetsregisteret/api/enheter'

type BrregEntity = {
  organisasjonsnummer?: string
  navn?: string
  organisasjonsform?: { kode?: string }
  stiftelsesdato?: string
  antallAnsatte?: number
  naeringskode1?: { beskrivelse?: string }
  hjemmeside?: string
  konkurs?: boolean
  underAvvikling?: boolean
  forretningsadresse?: { adresse?: string[]; postnummer?: string; poststed?: string; land?: string }
}

function fold(value: string) {
  return value.toLowerCase().replaceAll('æ', 'ae').replaceAll('ø', 'o').replaceAll('å', 'a')
}

function cityOf(entity: BrregEntity) {
  return (entity.forretningsadresse?.poststed ?? '').trim().toLowerCase().replace(/^./, (c) => c.toUpperCase())
}

function addressOf(entity: BrregEntity) {
  const a = entity.forretningsadresse
  if (!a) return ''
  return [(a.adresse ?? []).join(', '), [a.postnummer, a.poststed].filter(Boolean).join(' '), a.land]
    .filter(Boolean)
    .join(', ')
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new Error(`Register returned HTTP ${res.status}`)
  return (await res.json()) as T
}

/** Name or organisation-number search in Enhetsregisteret. Returns the same row shape as the local index. */
export async function searchRegistry(query: string): Promise<IndexRow[]> {
  const q = query.trim()
  if (q.length < 2) return []
  if (/^\d{9}$/.test(q)) {
    const one = await getJson<BrregEntity>(`${BRREG}/${q}`)
    return [[q, one.navn ?? q, cityOf(one), one.organisasjonsform?.kode ?? '', one.naeringskode1?.beskrivelse ?? '', 0, one.hjemmeside ? 1 : 0]]
  }
  const data = await getJson<{ _embedded?: { enheter?: BrregEntity[] } }>(
    `${BRREG}?navn=${encodeURIComponent(q)}&size=25`,
  )
  const tokens = fold(q).split(/\s+/).filter(Boolean)
  const rows = (data._embedded?.enheter ?? [])
    .filter((e) => e.organisasjonsnummer && e.navn && tokens.every((t) => fold(e.navn ?? '').includes(t)))
    .sort((a, b) => {
      const startA = fold(a.navn ?? '').startsWith(tokens[0]) ? 0 : 1
      const startB = fold(b.navn ?? '').startsWith(tokens[0]) ? 0 : 1
      return startA - startB || (a.navn ?? '').localeCompare(b.navn ?? '')
    })
    .slice(0, 8)
    .map((e): IndexRow => [
      e.organisasjonsnummer as string,
      e.navn as string,
      cityOf(e),
      e.organisasjonsform?.kode ?? '',
      e.naeringskode1?.beskrivelse ?? '',
      0,
      e.hjemmeside ? 1 : 0,
    ])
  return rows
}

/** Read one company straight from the register and describe it with the same source-backed shape as a crawled profile. */
export async function loadRegistryDoc(org: string): Promise<ExDoc> {
  const base = `${BRREG}/${org}`
  const entity = await getJson<BrregEntity>(base)
  const fetchedAt = new Date().toISOString()
  const address = addressOf(entity)
  const status = entity.konkurs ? 'Bankrupt' : entity.underAvvikling ? 'Under liquidation' : 'Active'

  const raw: [string, string, string, unknown][] = [
    ['official_legal_name', 'Legal name', 'navn', entity.navn],
    ['organisation_form', 'Organisation form', 'organisasjonsform.kode', entity.organisasjonsform?.kode],
    ['registered_address', 'Registered address', 'forretningsadresse', address || undefined],
    ['incorporation_date', 'Founded', 'stiftelsesdato', entity.stiftelsesdato],
    ['employees', 'Employees', 'antallAnsatte', entity.antallAnsatte],
    ['industry', 'Industry (NACE)', 'naeringskode1.beskrivelse', entity.naeringskode1?.beskrivelse],
    ['website', 'Website', 'hjemmeside', entity.hjemmeside],
    ['company_status', 'Status', 'konkurs', status],
  ]

  const facts: ExFact[] = []
  for (const [k, l, p, value] of raw) {
    if (value === undefined || value === null || value === '') continue
    facts.push({
      k,
      l,
      v: String(value),
      t: fetchedAt,
      p,
      s: await sha256Hex(JSON.stringify(value)),
      e: 'Read live from the Brønnøysund Register Centre in your browser for this request; nothing was inferred.',
    })
  }

  return {
    n: org,
    name: entity.navn ?? org,
    base,
    summary: '',
    hash: '',
    content_hash: '',
    update: { status: 'registry-only', changed: [] },
    registryOnly: true,
    missing: {
      website_check: 'The company’s own website has not been crawled, so no social links, news or jobs are shown.',
      annual_accounts: 'Annual accounts have not been fetched from Regnskapsregisteret for this company.',
    },
    facts,
    fin: null,
    web: null,
    news: [],
    jobs: [],
    social: [],
  }
}

export function money(value: number | null | undefined, currency?: string | null) {
  if (value === null || value === undefined) return '—'
  return `${currency ?? 'NOK'} ${new Intl.NumberFormat('en-GB').format(value)}`
}
