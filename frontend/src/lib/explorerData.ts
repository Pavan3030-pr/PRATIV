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
  social: { platform: string; url: string }[]
}

/** [orgnr, name, city, form, industry, hasAccounts, hasWebsite] */
export type IndexRow = [string, string, string, string, string, number, number]

export type CheckResult = { tone: 'ok' | 'warn' | 'info'; text: string }

let indexPromise: Promise<IndexRow[]> | null = null
const docs = new Map<string, Promise<ExDoc>>()
const live = new Map<string, Promise<unknown>>()

export function loadIndex() {
  indexPromise ??= fetch('/explore/index.json').then((r) => {
    if (!r.ok) throw new Error('Company index unavailable')
    return r.json() as Promise<IndexRow[]>
  })
  return indexPromise
}

export function loadDoc(org: string) {
  let p = docs.get(org)
  if (!p) {
    p = fetch(`/explore/c/${org}.json`).then((r) => {
      if (!r.ok) throw new Error('Company not found in this dataset')
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

const simplePath = /^[A-Za-z]+$/

/** Re-fetch the fact's own source and compare it with what was stored. Never claims more than it checked. */
export async function checkFact(fact: ExFact, base: string): Promise<CheckResult> {
  const url = fact.u ?? base
  let data: unknown
  try {
    data = await fetchLive(url)
  } catch {
    return { tone: 'info', text: 'Could not reach the source from this browser. Use “Open source” to check it directly.' }
  }
  const record = data as Record<string, unknown>
  const raw = simplePath.test(fact.p) ? record[fact.p] : undefined
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

export function money(value: number | null | undefined, currency?: string | null) {
  if (value === null || value === undefined) return '—'
  return `${currency ?? 'NOK'} ${new Intl.NumberFormat('en-GB').format(value)}`
}
