import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { ExDoc } from '../../lib/explorerData'
import { Explorer } from './Explorer'

const index = [
  ['984851006', 'DNB BANK ASA', 'Oslo', 'ASA', 'Banker', 1, 1, 7334],
  ['923609016', 'EQUINOR ASA', 'Stavanger', 'ASA', 'Utvinning', 1, 1, 21000],
]

function doc(n: string, name: string, over: Partial<ExDoc> = {}): ExDoc {
  return {
    n,
    name,
    base: `https://data.brreg.no/enhetsregisteret/api/enheter/${n}`,
    summary: `${name} reported revenue of NOK 1 000 000 for the period ending 2025-12-31 (Brønnøysund Regnskapsregisteret).`,
    hash: 'a'.repeat(64),
    content_hash: 'b'.repeat(64),
    update: { status: 'unchanged', changed: [] },
    missing: {},
    facts: [
      {
        k: 'employees',
        l: 'Employees',
        v: '7334',
        t: '2026-11-13T10:00:00Z',
        p: 'antallAnsatte',
        s: '',
        e: 'Read directly from the registry response.',
      },
      { k: 'company_status', l: 'Status', v: 'active', t: '2026-11-13T10:00:00Z', p: 'konkurs', s: '', e: '' },
    ],
    fin: null,
    web: { url: `https://${name.split(' ')[0].toLowerCase()}.no`, verified: true, by: 'organisation_number' },
    news: [],
    jobs: [],
    social: [],
    ...over,
  }
}

function json(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }),
  )
}

function mockApi(docs: ExDoc[], live: Record<string, unknown> = {}, search: Record<string, unknown>[] = []) {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/explore/index.json')) return json(index)
    const match = /\/explore\/c\/(\d{9})\.json/.exec(url)
    if (match) {
      const found = docs.find((d) => d.n === match[1])
      return found ? json(found) : Promise.resolve(new Response('no', { status: 404 }))
    }
    if (url.includes('/enhetsregisteret/api/enheter/')) {
      return Object.keys(live).length ? json(live) : Promise.resolve(new Response('no', { status: 404 }))
    }
    if (url.includes('/enhetsregisteret/api/enheter?')) return json({ _embedded: { enheter: search } })
    return Promise.resolve(new Response('no', { status: 404 }))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const TELENOR = {
  organisasjonsnummer: '982463718',
  navn: 'TELENOR ASA',
  organisasjonsform: { kode: 'ASA' },
  stiftelsesdato: '1996-11-07',
  antallAnsatte: 9000,
  naeringskode1: { beskrivelse: 'Trådløs telekommunikasjon' },
  forretningsadresse: { adresse: ['Snarøyveien 30'], postnummer: '1360', poststed: 'FORNEBU', land: 'Norge' },
}

describe('explorer company page', () => {
  it('shows the buyer summary, sourced facts and open roles', async () => {
    const company = doc('984851006', 'DNB BANK ASA', {
      jobs: [
        {
          title: 'Senior utvikler',
          url: 'https://www.dnb.no/jobb/senior-utvikler',
          at: '2026-10-05',
        },
      ],
    })
    window.location.hash = '#/explore/c/984851006'
    mockApi([company], { antallAnsatte: 7334 })
    render(<Explorer />)

    expect(await screen.findByRole('heading', { name: 'DNB BANK ASA' })).toBeInTheDocument()
    expect(screen.getByText(/reported revenue of NOK 1 000 000/)).toBeInTheDocument()
    expect(screen.getByText('Employees')).toBeInTheDocument()
    expect(screen.getByText('Open roles on the company site')).toBeInTheDocument()
    const job = screen.getByRole('link', { name: 'Senior utvikler' })
    expect(job).toHaveAttribute('href', 'https://www.dnb.no/jobb/senior-utvikler')
    expect(screen.getByText(/posted/)).toBeInTheDocument()
  })

  it('checks a registry fact against its live source', async () => {
    window.location.hash = '#/explore/c/984851006'
    mockApi([doc('984851006', 'DNB BANK ASA')], { antallAnsatte: 7334 })
    render(<Explorer />)

    await screen.findByRole('heading', { name: 'DNB BANK ASA' })
    await userEvent.click(screen.getAllByRole('button', { name: /check source/i })[0])
    expect(await screen.findByText(/Verified: the live source shows the same value/)).toBeInTheDocument()
  })

  it('explains a company that is neither in the dataset nor in the register', async () => {
    window.location.hash = '#/explore/c/999999999'
    mockApi([])
    render(<Explorer />)
    expect(await screen.findByText('Company not found')).toBeInTheDocument()
  })

  it('reads a company that is outside the dataset straight from the register', async () => {
    window.location.hash = '#/explore/c/982463718'
    mockApi([], TELENOR)
    render(<Explorer />)

    expect(await screen.findByRole('heading', { name: 'TELENOR ASA' })).toBeInTheDocument()
    expect(screen.getByText('Registry only')).toBeInTheDocument()
    expect(screen.getByText(/not in the crawled dataset/)).toBeInTheDocument()
    expect(screen.getByText('Trådløs telekommunikasjon')).toBeInTheDocument()
    expect(screen.getByText('9000')).toBeInTheDocument()
    expect(screen.queryByText('Company not found')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Official record/ })).toHaveAttribute(
      'href',
      'https://data.brreg.no/enhetsregisteret/api/enheter/982463718',
    )
  })
})

describe('how it works page', () => {
  it('states the sources and the limits', async () => {
    window.location.hash = '#/explore/about'
    mockApi([])
    render(<Explorer />)
    expect(await screen.findByRole('heading', { name: 'How this works' })).toBeInTheDocument()
    expect(screen.getAllByText(/Enhetsregisteret/).length).toBeGreaterThan(0)
    expect(screen.getByText(/ATS that renders solely in the browser/)).toBeInTheDocument()
    expect(screen.getByText(/shared careers page/)).toBeInTheDocument()
    expect(screen.getByText(/never estimated/)).toBeInTheDocument()
  })
})

describe('explorer search', () => {
  it('filters the index and starts a comparison', async () => {
    window.location.hash = '#/explore'
    mockApi([])
    render(<Explorer />)

    await screen.findByText('DNB BANK ASA')
    await userEvent.type(screen.getByRole('searchbox'), 'equinor')
    expect(screen.getByText('EQUINOR ASA')).toBeInTheDocument()
    expect(screen.queryByText('DNB BANK ASA')).not.toBeInTheDocument()

    const row = screen.getByText('EQUINOR ASA').closest('li') as HTMLElement
    await userEvent.click(within(row).getByRole('button', { name: 'Compare: add to comparison' }))
    expect(screen.getByText(/selected — pick one more to compare/)).toBeInTheDocument()
  })
})

describe('registry search fallback', () => {
  it('offers register matches when nothing in the crawl matches', async () => {
    window.location.hash = '#/explore'
    mockApi([], {}, [{ organisasjonsnummer: '982463718', navn: 'TELENOR ASA', organisasjonsform: { kode: 'ASA' } }])
    render(<Explorer />)

    await screen.findByText('DNB BANK ASA')
    await userEvent.type(screen.getByRole('searchbox'), 'telenor')
    expect(await screen.findByText(/Found in Enhetsregisteret/)).toBeInTheDocument()
    const link = screen.getAllByRole('link', { name: /TELENOR ASA/ })[0]
    expect(link).toHaveAttribute('href', '#/explore/c/982463718')
    expect(screen.getByText(/no website, news or jobs/)).toBeInTheDocument()
  })

  it('reports a register failure instead of pretending the company is missing', async () => {
    window.location.hash = '#/explore'
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/explore/index.json')) return json(index)
      return Promise.resolve(new Response('no', { status: 503 }))
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<Explorer />)

    await screen.findByText('DNB BANK ASA')
    await userEvent.type(screen.getByRole('searchbox'), 'telenor')
    expect(await screen.findByText(/live register search failed/)).toBeInTheDocument()
  })
})

describe('explorer compare', () => {
  it('marks missing and differing values side by side', async () => {
    const a = doc('111111111', 'ALFA AS')
    const b = doc('222222222', 'BETA AS', {
      facts: [{ k: 'company_status', l: 'Status', v: 'bankrupt', t: '2026-11-13T10:00:00Z', p: 'konkurs', s: '', e: '' }],
    })
    window.location.hash = '#/explore/compare/111111111/222222222'
    mockApi([a, b])
    render(<Explorer />)

    expect(await screen.findByRole('heading', { name: 'Compare' })).toBeInTheDocument()
    expect(screen.getAllByText('ALFA AS').length).toBeGreaterThan(0)
    expect(screen.getAllByText('BETA AS').length).toBeGreaterThan(0)
    expect(screen.getByText('Not available')).toBeInTheDocument()
    expect(screen.getByText(/Highlighted rows differ/)).toBeInTheDocument()
  })
})
