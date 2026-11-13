import { describe, expect, it, vi } from 'vitest'
import { checkFact, loadDoc, loadIndex, money, sourceLabel, type ExFact } from './explorerData'

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

describe('data loading', () => {
  it('loads and caches a company document', async () => {
    const fetchMock = vi.fn(() => json({ n: '999999991', facts: [] }))
    vi.stubGlobal('fetch', fetchMock)
    const first = await loadDoc('999999991')
    const second = await loadDoc('999999991')
    expect(first).toBe(second)
    expect(fetchMock).toHaveBeenCalledTimes(1)
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
