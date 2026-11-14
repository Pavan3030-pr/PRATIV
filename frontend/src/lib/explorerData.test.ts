import { describe, expect, it, vi } from 'vitest'
import {
  checkFact,
  factsCsv,
  loadDoc,
  loadIndex,
  loadRegistryDoc,
  money,
  searchRegistry,
  sourceLabel,
  type ExDoc,
  type ExFact,
} from './explorerData'

const base = 'https://data.brreg.no/enhetsregisteret/api/enheter/984851006'

function fact(over: Partial<ExFact> = {}): ExFact {
  return {
    k: 'employees',
    l: 'Employees',
    v: '42',
    t: '2026-01-01T00:00:00Z',
    p: 'antallAnsatte',
    s: '',
    e: '',
    ...over,
  }
}

function json(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }),
  )
}

describe('sourceLabel', () => {
  it('names the register behind each kind of source URL', () => {
    expect(sourceLabel('https://data.brreg.no/regnskapsregisteret/regnskap/1')).toContain('Regnskapsregisteret')
    expect(sourceLabel('https://data.brreg.no/enhetsregisteret/api/enheter/1/roller')).toBe('Enhetsregisteret roles')
    expect(sourceLabel('https://data.brreg.no/enhetsregisteret/api/underenheter/1')).toBe('Enhetsregisteret sub-units')
    expect(sourceLabel('https://data.brreg.no/enhetsregisteret/api/enheter/1')).toBe('Enhetsregisteret')
    expect(sourceLabel('https://acme.no/karriere')).toBe('acme.no')
    expect(sourceLabel('not a url')).toBe('Source')
  })
})

describe('money', () => {
  it('formats filed figures and keeps missing ones explicit', () => {
    expect(money(1234567, 'NOK')).toBe('NOK 1,234,567')
    expect(money(null)).toBe('—')
    expect(money(undefined)).toBe('—')
  })
})

describe('checkFact', () => {
  it('does not pretend to verify facts that come from the company website', async () => {
    const result = await checkFact(fact({ k: 'website', u: 'https://acme.no', v: 'https://acme.no' }), base)
    expect(result.tone).toBe('info')
    expect(result.text).toContain('company’s own website')
  })

  it('confirms a registry fact when the live source shows the stored value', async () => {
    vi.stubGlobal('fetch', vi.fn(() => json({ antallAnsatte: 42 })))
    const result = await checkFact(fact({ u: `${base}/ok` }), base)
    expect(result.tone).toBe('ok')
    expect(result.text).toContain('same value')
  })

  it('warns when the source has moved on from the stored value', async () => {
    vi.stubGlobal('fetch', vi.fn(() => json({ antallAnsatte: 99 })))
    const result = await checkFact(fact({ u: `${base}/changed` }), base)
    expect(result.tone).toBe('warn')
    expect(result.text).toContain('99')
  })

  it('says so when the source cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('offline'))))
    const result = await checkFact(fact({ u: `${base}/down`, k: 'official_legal_name', p: 'navn' }), base)
    expect(result.tone).toBe('info')
    expect(result.text).toContain('Could not reach the source')
  })
})

describe('factsCsv', () => {
  it('writes every fact with its source and quotes unsafe cells', () => {
    const doc = {
      base: 'https://data.brreg.no/enhetsregisteret/api/enheter/984851006',
      facts: [
        {
          k: 'official_legal_name',
          l: 'Legal name',
          v: 'ACME, "NORD" AS',
          t: '2026-11-13T10:00:00Z',
          p: 'navn',
          s: 'abc123',
          e: 'Read from the registry.\nSecond line.',
          u: 'https://data.brreg.no/enhetsregisteret/api/enheter/984851006',
        },
      ],
    } as unknown as ExDoc
    const csv = factsCsv(doc)
    expect(csv.split('\n')[0]).toBe('field,label,value,source_url,source_field,retrieved_at,value_sha256,explanation')
    expect(csv).toContain('"ACME, ""NORD"" AS"')
    expect(csv).toContain('"Read from the registry.\nSecond line."')
    expect(csv.endsWith('\n')).toBe(true)
  })
})

const ENTITY = {
  organisasjonsnummer: '982463718',
  navn: 'TELENOR ASA',
  organisasjonsform: { kode: 'ASA' },
  stiftelsesdato: '1996-11-07',
  antallAnsatte: 9000,
  naeringskode1: { beskrivelse: 'Trådløs telekommunikasjon' },
  hjemmeside: 'www.telenor.no/',
  konkurs: false,
  forretningsadresse: { adresse: ['Snarøyveien 30'], postnummer: '1360', poststed: 'FORNEBU', land: 'Norge' },
}

describe('live registry fallback', () => {
  it('finds companies by name, keeping only real matches and putting prefix matches first', async () => {
    const fetchMock = vi.fn((_url: RequestInfo | URL) =>
      json({
        _embedded: {
          enheter: [
            { organisasjonsnummer: '999999991', navn: 'NITO TELE', forretningsadresse: { poststed: 'OSLO' } },
            { ...ENTITY },
            { organisasjonsnummer: '931479849', navn: 'TELENOR CDP AS', naeringskode1: { beskrivelse: 'Utleie' } },
            { organisasjonsnummer: '999999992', navn: 'TELENOR FESTEKONTRAKTER AS' },
          ],
        },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const rows = await searchRegistry('telenor')
    expect(fetchMock.mock.calls[0][0]).toContain('navn=telenor')
    expect(rows.map((r) => r[1])).toEqual(['TELENOR ASA', 'TELENOR CDP AS', 'TELENOR FESTEKONTRAKTER AS'])
    expect(rows[0]).toEqual(['982463718', 'TELENOR ASA', 'Fornebu', 'ASA', 'Trådløs telekommunikasjon', 0, 1])
  })

  it('looks up a 9-digit organisation number directly and ignores shorter queries', async () => {
    const fetchMock = vi.fn((_url: RequestInfo | URL) => json(ENTITY))
    vi.stubGlobal('fetch', fetchMock)
    expect(await searchRegistry('t')).toEqual([])
    expect(fetchMock).not.toHaveBeenCalled()
    const rows = await searchRegistry('982463718')
    expect(fetchMock.mock.calls[0][0]).toContain('/enheter/982463718')
    expect(rows[0][1]).toBe('TELENOR ASA')
  })

  it('fails loudly when the register itself is down, so the UI never reports a false "no match"', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('no', { status: 503 }))))
    await expect(searchRegistry('telenor')).rejects.toThrow('HTTP 503')
    await expect(searchRegistry('982463718')).rejects.toThrow('HTTP 503')
  })

  it('describes a live register record with source, path, timestamp and hash', async () => {
    vi.stubGlobal('fetch', vi.fn(() => json(ENTITY)))
    const doc = await loadRegistryDoc('982463718')
    expect(doc.registryOnly).toBe(true)
    expect(doc.name).toBe('TELENOR ASA')
    expect(doc.base).toBe('https://data.brreg.no/enhetsregisteret/api/enheter/982463718')
    const byKey = Object.fromEntries(doc.facts.map((f) => [f.k, f]))
    expect(byKey.official_legal_name.v).toBe('TELENOR ASA')
    expect(byKey.industry.p).toBe('naeringskode1.beskrivelse')
    expect(byKey.industry.v).toBe('Trådløs telekommunikasjon')
    expect(byKey.registered_address.v).toBe('Snarøyveien 30, 1360 FORNEBU, Norge')
    expect(byKey.company_status.v).toBe('Active')
    expect(byKey.website.v).toBe('www.telenor.no/')
    for (const f of doc.facts) {
      expect(f.t).toMatch(/^\d{4}-\d{2}-\d{2}T/)
      expect(f.s).toMatch(/^[0-9a-f]{64}$/)
      expect(f.u).toBeUndefined() // source URL is the document's own registry record
    }
    expect(doc.fin).toBeNull()
    expect(doc.jobs).toEqual([])
    expect(doc.missing.website_check).toContain('not been crawled')
  })

  it('says bankruptcy when the register does', async () => {
    vi.stubGlobal('fetch', vi.fn(() => json({ ...ENTITY, konkurs: true })))
    const doc = await loadRegistryDoc('982463718')
    expect(doc.facts.find((f) => f.k === 'company_status')?.v).toBe('Bankrupt')
  })

  it('verifies a nested field path against the live source', async () => {
    vi.stubGlobal('fetch', vi.fn(() => json({ antallAnsatte: 42, naeringskode1: { beskrivelse: 'Bank' } })))
    const result = await checkFact(
      fact({ p: 'naeringskode1.beskrivelse', v: 'Bank', s: '' }),
      base,
    )
    expect(result.tone).toBe('ok')
  })
})

describe('data loading', () => {
  it('loads and caches a company document', async () => {
    const fetchMock = vi.fn(() => json({ n: '999999991', facts: [] }))
    vi.stubGlobal('fetch', fetchMock)
    const first = await loadDoc('999999991')
    const second = await loadDoc('999999991')
    expect(first).toBe(second)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('treats a single-page app HTML answer as a missing profile, not a document', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response('<!doctype html>', { status: 200, headers: { 'Content-Type': 'text/html; charset=utf-8' } }),
        ),
      ),
    )
    await expect(loadDoc('999999993')).rejects.toThrow('Company not found')
  })

  it('reports an unavailable document without poisoning the cache', async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => Promise.resolve(new Response('no', { status: 404 })))
      .mockImplementationOnce(() => json({ n: '999999992', facts: [] }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(loadDoc('999999992')).rejects.toThrow('Company not found')
    await expect(loadDoc('999999992')).resolves.toMatchObject({ n: '999999992' })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('retries the index after a failed first load', async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => Promise.resolve(new Response('no', { status: 503 })))
      .mockImplementationOnce(() => json([['984851006', 'DNB BANK ASA', 'Oslo', 'ASA', 'Banker', 1, 1]]))
    vi.stubGlobal('fetch', fetchMock)
    await expect(loadIndex()).rejects.toThrow('Company index unavailable')
    await expect(loadIndex()).resolves.toHaveLength(1)
  })
})
