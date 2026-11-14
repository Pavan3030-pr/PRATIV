import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowLeft,
  Check,
  ChevronDown,
  Copy,
  Download,
  ExternalLink,
  LoaderCircle,
  Plus,
  Search,
  ShieldCheck,
  X,
} from 'lucide-react'
import { Brand } from '../Brand'
import { Badge, Button } from '../ui'
import { formatDate } from '../../lib/api'
import { cn } from '../../lib/cn'
import {
  checkFact,
  downloadText,
  factsCsv,
  loadDoc,
  loadIndex,
  loadRegistryDoc,
  money,
  searchRegistry,
  sourceLabel,
  type CheckResult,
  type ExDoc,
  type ExFact,
  type IndexRow,
} from '../../lib/explorerData'

type Route =
  | { page: 'home' }
  | { page: 'about' }
  | { page: 'company'; org: string }
  | { page: 'compare'; a: string; b: string }

function parseRoute(): Route {
  const parts = window.location.hash.replace(/^#\/?/, '').split('/').filter(Boolean)
  if (parts[1] === 'about') return { page: 'about' }
  if (parts[1] === 'c' && /^\d{9}$/.test(parts[2] ?? '')) return { page: 'company', org: parts[2] }
  if (parts[1] === 'compare' && /^\d{9}$/.test(parts[2] ?? '') && /^\d{9}$/.test(parts[3] ?? '')) {
    return { page: 'compare', a: parts[2], b: parts[3] }
  }
  return { page: 'home' }
}

/** Set by the submit step only if the site was actually built with JBox. */
const CREDIT = ''

const go = (path: string) => {
  window.location.hash = path
  window.scrollTo({ top: 0 })
}

function Shell({ children, wide = false }: { children: React.ReactNode; wide?: boolean }) {
  return (
    <div className="min-h-screen bg-canvas pb-28">
      <header className="sticky top-0 z-30 border-b border-line bg-paper/90 backdrop-blur-md">
        <div className={cn('mx-auto flex h-14 items-center justify-between gap-4 px-4', wide ? 'max-w-5xl' : 'max-w-3xl')}>
          <a href="#/explore" aria-label="Signalpost explorer home">
            <Brand compact />
          </a>
          <a href="#/explore/about" className="text-[13px] text-muted hover:text-ink">
            How it works
          </a>
        </div>
      </header>
      <main className={cn('mx-auto px-4 py-6 sm:py-10', wide ? 'max-w-5xl' : 'max-w-3xl')}>{children}</main>
      <footer className={cn('mx-auto px-4 pb-6 text-[12px] text-faint', wide ? 'max-w-5xl' : 'max-w-3xl')}>
        Data: Brønnøysund Register Centre (Brreg), collected by the Signalpost agent{CREDIT}
      </footer>
    </div>
  )
}

function CompareBar({ picked, names, clear }: { picked: string[]; names: Record<string, string>; clear: () => void }) {
  if (picked.length === 0) return null
  return (
    <div
      className="fixed inset-x-0 bottom-0 z-40 border-t border-line-strong bg-paper px-4 pt-3 shadow-lift"
      style={{ paddingBottom: 'calc(0.75rem + env(safe-area-inset-bottom, 0px))' }}
    >
      <div className="mx-auto flex max-w-3xl items-center justify-between gap-3">
        <p className="min-w-0 truncate text-[13px] text-graphite" aria-live="polite">
          {picked.length < 2
            ? `${names[picked[0]] ?? picked[0]} selected — pick one more to compare`
            : `${names[picked[0]] ?? picked[0]} vs ${names[picked[1]] ?? picked[1]}`}
        </p>
        <div className="flex shrink-0 gap-2">
          <Button variant="ghost" size="sm" onClick={clear} aria-label="Clear comparison">
            <X size={14} aria-hidden="true" />
          </Button>
          <Button size="sm" disabled={picked.length < 2} onClick={() => go(`/explore/compare/${picked[0]}/${picked[1]}`)}>
            Compare
          </Button>
        </div>
      </div>
    </div>
  )
}

function PickButton({ org, picked, toggle }: { org: string; picked: string[]; toggle: (o: string) => void }) {
  const on = picked.includes(org)
  return (
    <button
      type="button"
      onClick={() => toggle(org)}
      aria-pressed={on}
      aria-label={on ? 'Added: remove from comparison' : 'Compare: add to comparison'}
      className={cn(
        'inline-flex h-11 min-w-11 items-center justify-center gap-1.5 rounded-control border px-3 text-[12px] font-medium transition-colors',
        on ? 'border-accent bg-accent-soft text-accent' : 'border-line-strong bg-paper text-graphite hover:bg-sunken',
      )}
    >
      {on ? <Check size={15} aria-hidden="true" /> : <Plus size={15} aria-hidden="true" />}
      <span className="hidden sm:inline">{on ? 'Added' : 'Compare'}</span>
    </button>
  )
}

type RegistrySearch = { q: string; rows: IndexRow[]; busy: boolean; error?: string }

function Home({ index, picked, toggle }: { index: IndexRow[] | null; picked: string[]; toggle: (o: string) => void }) {
  const [q, setQ] = useState('')
  const [onlyAccounts, setOnlyAccounts] = useState(false)
  const [onlyWeb, setOnlyWeb] = useState(false)
  const [limit, setLimit] = useState(30)
  const [reg, setReg] = useState<RegistrySearch>({ q: '', rows: [], busy: false })

  const hay = useMemo(
    () => (index ?? []).map((r) => `${r[1]} ${r[0]} ${r[2]} ${r[4]}`.toLowerCase()),
    [index],
  )

  const results = useMemo(() => {
    if (!index) return []
    const tokens = q.toLowerCase().split(/\s+/).filter(Boolean)
    const out: IndexRow[] = []
    index.forEach((row, i) => {
      if (onlyAccounts && !row[5]) return
      if (onlyWeb && !row[6]) return
      if (tokens.every((t) => hay[i].includes(t))) out.push(row)
    })
    const first = tokens[0] ?? ''
    if (first) {
      return out.sort((a, b) => Number(b[1].toLowerCase().startsWith(first)) - Number(a[1].toLowerCase().startsWith(first)))
    }
    // Browsing with no search: the register's employee count puts the largest employers first.
    return out.sort((a, b) => (b[7] ?? 0) - (a[7] ?? 0) || a[1].localeCompare(b[1]))
  }, [index, hay, q, onlyAccounts, onlyWeb])

  const trimmed = q.trim()
  const registryChecked = reg.q === trimmed && !reg.busy && !reg.error

  // Nothing in the crawl for this query: ask the official register so a real company is never reported missing.
  useEffect(() => {
    if (index === null || results.length > 0 || trimmed.length < 2) return
    let alive = true
    const timer = window.setTimeout(() => {
      setReg({ q: trimmed, rows: [], busy: true })
      searchRegistry(trimmed)
        .then((rows) => alive && setReg({ q: trimmed, rows, busy: false }))
        .catch((e: Error) => alive && setReg({ q: trimmed, rows: [], busy: false, error: e.message }))
    }, 350)
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
  }, [index, trimmed, results.length])

  const chip = (on: boolean) =>
    cn(
      'h-9 rounded-full border px-3.5 text-[12.5px] font-medium transition-colors',
      on ? 'border-accent bg-accent-soft text-accent' : 'border-line-strong bg-paper text-graphite hover:bg-sunken',
    )

  return (
    <>
      <p className="kicker text-accent">Norwegian company register</p>
      <h1 className="mt-3 text-[clamp(1.75rem,5vw,2.5rem)] leading-tight font-semibold tracking-[-0.03em]">
        Find a company. See where every fact came from.
      </h1>
      <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-graphite">
        {index ? index.length.toLocaleString('en-GB') : '1,000+'} profiles. Each fact links to its official source with the
        retrieval date, so you can check it yourself.
      </p>

      <div className="relative mt-6">
        <Search size={18} className="pointer-events-none absolute top-1/2 left-4 -translate-y-1/2 text-muted" aria-hidden="true" />
        <input
          type="search"
          value={q}
          onChange={(e) => {
            setQ(e.target.value)
            setLimit(30)
          }}
          placeholder="Company name, org. number or town"
          aria-label="Search companies"
          autoComplete="off"
          inputMode="search"
          className="h-14 w-full rounded-card border border-line-strong bg-paper pr-4 pl-11 text-base shadow-panel outline-none focus:border-accent"
        />
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" aria-pressed={onlyAccounts} className={chip(onlyAccounts)} onClick={() => setOnlyAccounts((v) => !v)}>
          Has annual accounts
        </button>
        <button type="button" aria-pressed={onlyWeb} className={chip(onlyWeb)} onClick={() => setOnlyWeb((v) => !v)}>
          Has website
        </button>
      </div>

      {!index ? (
        <p className="mt-8 flex items-center gap-2 text-[14px] text-muted" role="status">
          <LoaderCircle size={16} className="animate-spin" aria-hidden="true" /> Loading companies…
        </p>
      ) : (
        <>
          <p className="mt-6 text-[12.5px] text-muted" aria-live="polite">
            {results.length.toLocaleString('en-GB')} {results.length === 1 ? 'company' : 'companies'}
          </p>
          <ul className="mt-2 grid gap-2">
            {results.slice(0, limit).map((r) => (
              <li key={r[0]} className="flex items-stretch gap-2">
                <a
                  href={`#/explore/c/${r[0]}`}
                  className="min-w-0 flex-1 rounded-panel border border-line bg-paper px-4 py-3 transition-colors hover:border-line-strong"
                >
                  <span className="block truncate text-[15px] font-medium">{r[1]}</span>
                  <span className="mt-0.5 block truncate text-[12.5px] text-muted">
                    {r[0]}
                    {r[2] ? ` · ${r[2]}` : ''}
                    {r[3] ? ` · ${r[3]}` : ''}
                    {r[5] ? ' · accounts' : ''}
                  </span>
                </a>
                <PickButton org={r[0]} picked={picked} toggle={toggle} />
              </li>
            ))}
          </ul>
          {results.length === 0 ? (
            <div className="mt-6">
              <p className="text-[14px] text-graphite">
                No crawled profile matches “{trimmed}”. Checking the official register…
              </p>
              {trimmed.length >= 2 && reg.q !== trimmed ? (
                <p className="mt-3 flex items-center gap-2 text-[13px] text-muted" role="status">
                  <LoaderCircle size={14} className="animate-spin" aria-hidden="true" /> Searching Enhetsregisteret
                </p>
              ) : reg.busy ? (
                <p className="mt-3 flex items-center gap-2 text-[13px] text-muted" role="status">
                  <LoaderCircle size={14} className="animate-spin" aria-hidden="true" /> Searching Enhetsregisteret
                </p>
              ) : reg.error ? (
                <p className="mt-3 rounded-control bg-warning-soft px-3 py-2 text-[13px] text-warning">
                  The live register search failed ({reg.error}). Try fewer words, or a 9-digit organisation number.
                </p>
              ) : reg.rows.length > 0 ? (
                <>
                  <p className="mt-5 text-[12px] font-medium tracking-wide text-muted uppercase">
                    Found in Enhetsregisteret · read live, not crawled yet
                  </p>
                  <ul className="mt-2 grid gap-2">
                    {reg.rows.map((r) => (
                      <li key={r[0]}>
                        <a
                          href={`#/explore/c/${r[0]}`}
                          className="block rounded-panel border border-dashed border-line-strong bg-paper px-4 py-3 transition-colors hover:bg-sunken"
                        >
                          <span className="block truncate text-[15px] font-medium">{r[1]}</span>
                          <span className="mt-0.5 block truncate text-[12.5px] text-muted">
                            {r[0]}
                            {r[2] ? ` · ${r[2]}` : ''}
                            {r[3] ? ` · ${r[3]}` : ''}
                          </span>
                        </a>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-2 text-[12px] text-faint">
                    These records are not part of the crawl, so they show register fields only — no website, news or jobs.
                  </p>
                </>
              ) : registryChecked ? (
                <p className="mt-3 text-[14px] text-graphite">
                  The register has no active company matching that. Check the spelling, or search the 9-digit organisation number.
                </p>
              ) : null}
            </div>
          ) : null}
          {results.length > limit ? (
            <div className="mt-4 text-center">
              <Button variant="secondary" size="sm" onClick={() => setLimit((l) => l + 50)}>
                Show more
              </Button>
            </div>
          ) : null}
        </>
      )}
    </>
  )
}

function useDoc(org: string) {
  const [state, setState] = useState<{ org: string; doc?: ExDoc; error?: string } | null>(null)
  useEffect(() => {
    let alive = true
    loadDoc(org)
      .then((doc) => alive && setState({ org, doc }))
      .catch((e: Error) => alive && setState({ org, error: e.message }))
    return () => {
      alive = false
    }
  }, [org])
  return state?.org === org ? state : null
}

function SourceLine({ fact, base }: { fact: ExFact; base: string }) {
  const url = fact.u ?? base
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex min-h-8 items-center gap-1 text-[12.5px] text-accent hover:underline"
    >
      {sourceLabel(url)} · {fact.t ? formatDate(fact.t) : 'date n/a'}
      <ExternalLink size={12} aria-hidden="true" />
    </a>
  )
}

function FactRow({ fact, base }: { fact: ExFact; base: string }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<CheckResult | null>(null)

  async function run() {
    setBusy(true)
    setOpen(true)
    setResult(await checkFact(fact, base))
    setBusy(false)
  }

  const isSite = fact.k === 'website' && fact.v
  return (
    <li className="border-b border-line px-4 py-4 last:border-b-0 sm:px-5">
      <p className="text-[12px] font-medium tracking-wide text-muted uppercase">{fact.l}</p>
      <p className="mt-1 text-[15.5px] leading-snug font-medium [overflow-wrap:anywhere]">
        {isSite ? (
          <a className="text-accent hover:underline" target="_blank" rel="noopener noreferrer" href={fact.v.startsWith('http') ? fact.v : `https://${fact.v}`}>
            {fact.v}
          </a>
        ) : (
          fact.v || '—'
        )}
      </p>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1">
        <SourceLine fact={fact} base={base} />
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="inline-flex min-h-8 items-center gap-1 text-[12.5px] font-medium text-graphite hover:text-ink disabled:opacity-50"
        >
          {busy ? <LoaderCircle size={13} className="animate-spin" aria-hidden="true" /> : <ShieldCheck size={13} aria-hidden="true" />}
          Check source
        </button>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="inline-flex min-h-8 items-center gap-1 text-[12.5px] text-muted hover:text-ink"
        >
          How we know <ChevronDown size={13} className={cn('transition-transform', open && 'rotate-180')} aria-hidden="true" />
        </button>
      </div>
      <div aria-live="polite">
        {result ? (
          <p
            className={cn(
              'mt-2 rounded-control px-3 py-2 text-[12.5px] leading-snug',
              result.tone === 'ok' && 'bg-success-soft text-success',
              result.tone === 'warn' && 'bg-warning-soft text-warning',
              result.tone === 'info' && 'bg-sunken text-graphite',
            )}
          >
            {result.text}
          </p>
        ) : null}
      </div>
      {open ? (
        <dl className="mt-2 grid gap-1.5 rounded-control bg-sunken p-3 text-[12.5px] text-graphite">
          <div>
            <dt className="inline font-medium text-ink">Explanation: </dt>
            <dd className="inline">{fact.e || 'Read directly from the source record.'}</dd>
          </div>
          <div>
            <dt className="inline font-medium text-ink">Field in source: </dt>
            <dd className="inline font-mono text-[12px] [overflow-wrap:anywhere]">{fact.p}</dd>
          </div>
          <div>
            <dt className="inline font-medium text-ink">Retrieved: </dt>
            <dd className="inline">{fact.t || 'n/a'}</dd>
          </div>
          {fact.s ? (
            <div>
              <dt className="inline font-medium text-ink">Value SHA-256: </dt>
              <dd className="inline font-mono text-[11.5px] break-all">{fact.s}</dd>
            </div>
          ) : null}
        </dl>
      ) : null}
    </li>
  )
}

function CompanyPage({ org, picked, toggle }: { org: string; picked: string[]; toggle: (o: string) => void }) {
  const state = useDoc(org)
  const [copied, setCopied] = useState(false)
  const [reg, setReg] = useState<{ org: string; doc?: ExDoc; error?: string } | null>(null)

  // Not in the crawled dataset: read the company from Enhetsregisteret instead of saying it does not exist.
  useEffect(() => {
    if (!state?.error) return
    let alive = true
    loadRegistryDoc(org)
      .then((doc) => alive && setReg({ org, doc }))
      .catch((e: Error) => alive && setReg({ org, error: e.message }))
    return () => {
      alive = false
    }
  }, [org, state?.error])

  if (!state) return <Loading />
  const d = state.doc ?? (reg?.org === org ? reg.doc : undefined)
  if (!d) {
    if (reg?.org === org && reg.error) {
      return <NotFound message={`${state.error ?? 'Not in this dataset'}. The live register lookup also failed: ${reg.error}`} />
    }
    return <Loading label={state.error ? 'Not in the crawled dataset — reading Enhetsregisteret…' : undefined} />
  }
  const active = (d.facts.find((f) => f.k === 'company_status')?.v ?? '').toLowerCase().startsWith('active')
  const retrieved = d.facts[0]?.t

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(window.location.href)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      // Clipboard access can be blocked; the URL is still in the address bar.
    }
  }

  return (
    <>
      <a href="#/explore" className="inline-flex min-h-10 items-center gap-1.5 text-[13px] text-muted hover:text-ink">
        <ArrowLeft size={14} aria-hidden="true" /> All companies
      </a>
      <h1 className="mt-2 text-[clamp(1.5rem,4.5vw,2.25rem)] leading-tight font-semibold tracking-[-0.03em] [overflow-wrap:anywhere]">
        {d.name}
      </h1>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Badge>Org. nr {d.n}</Badge>
        <Badge tone={active ? 'success' : 'warning'}>{active ? 'Active' : 'Check status'}</Badge>
        {retrieved ? <Badge>Retrieved {formatDate(retrieved)}</Badge> : null}
        {d.registryOnly ? (
          <Badge tone="neutral">Registry only</Badge>
        ) : d.update.status ? (
          <Badge tone={d.update.status === 'changed' ? 'warning' : 'neutral'}>Update: {d.update.status}</Badge>
        ) : null}
      </div>

      {d.registryOnly ? (
        <p className="mt-4 rounded-panel border border-line-strong bg-sunken px-4 py-3 text-[13px] leading-relaxed text-graphite">
          <span className="font-medium text-ink">This company is not in the crawled dataset.</span> The fields below were read
          from Enhetsregisteret in this request, so each one links to the official record and carries its retrieval time.
          The company’s own website, news, job postings and annual accounts need a crawler run and are not shown.
        </p>
      ) : null}
      <div className="mt-4 flex flex-wrap gap-2">
        <PickButton org={d.n} picked={picked} toggle={toggle} />
        <a
          href={d.base}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex h-11 items-center gap-1.5 rounded-control border border-line-strong bg-paper px-3 text-[12.5px] font-medium text-graphite hover:bg-sunken"
        >
          Official record <ExternalLink size={13} aria-hidden="true" />
        </a>
        <button
          type="button"
          onClick={copyLink}
          className="inline-flex h-11 items-center gap-1.5 rounded-control border border-line-strong bg-paper px-3 text-[12.5px] font-medium text-graphite hover:bg-sunken"
        >
          {copied ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}
          {copied ? 'Link copied' : 'Copy link'}
        </button>
        <button
          type="button"
          onClick={() => downloadText(`${d.n}-${d.name.replace(/[^A-Za-z0-9]+/g, '-').toLowerCase()}.csv`, factsCsv(d), 'text/csv;charset=utf-8')}
          className="inline-flex h-11 items-center gap-1.5 rounded-control border border-line-strong bg-paper px-3 text-[12.5px] font-medium text-graphite hover:bg-sunken"
        >
          <Download size={13} aria-hidden="true" /> CSV
        </button>
        <button
          type="button"
          onClick={() => downloadText(`${d.n}-profile.json`, JSON.stringify(d, null, 2), 'application/json;charset=utf-8')}
          className="inline-flex h-11 items-center gap-1.5 rounded-control border border-line-strong bg-paper px-3 text-[12.5px] font-medium text-graphite hover:bg-sunken"
        >
          <Download size={13} aria-hidden="true" /> JSON
        </button>
      </div>

      {d.summary ? <p className="mt-5 rounded-panel border border-line bg-paper p-4 text-[14px] leading-relaxed text-graphite">{d.summary}</p> : null}

      <h2 className="mt-8 mb-2 text-[13px] font-semibold tracking-wide text-muted uppercase">Facts and their sources</h2>
      <ul className="overflow-hidden rounded-panel border border-line bg-paper" aria-label="Facts and their sources">
        {d.facts.map((f, i) => (
          <FactRow key={`${f.k}-${i}`} fact={f} base={d.base} />
        ))}
      </ul>

      {d.fin && d.fin.period_end ? (
        <>
          <h2 className="mt-8 mb-2 text-[13px] font-semibold tracking-wide text-muted uppercase">Latest annual accounts</h2>
          <div className="overflow-x-auto rounded-panel border border-line bg-paper">
            <table className="w-full min-w-[420px] text-left text-[13.5px]">
              <thead className="bg-sunken text-[12px] text-muted">
                <tr>
                  <th className="px-4 py-2 font-medium">Period</th>
                  <th className="px-4 py-2 font-medium">Revenue</th>
                  <th className="px-4 py-2 font-medium">Operating</th>
                  <th className="px-4 py-2 font-medium">Net</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="px-4 py-3">{d.fin.period_end}</td>
                  <td className="px-4 py-3">{money(d.fin.revenue, d.fin.currency)}</td>
                  <td className="px-4 py-3">{money(d.fin.operating_result, d.fin.currency)}</td>
                  <td className="px-4 py-3">{money(d.fin.net_result, d.fin.currency)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          {d.fin.source_url ? (
            <a className="mt-2 inline-flex min-h-8 items-center gap-1 text-[12.5px] text-accent hover:underline" href={d.fin.source_url} target="_blank" rel="noopener noreferrer">
              Regnskapsregisteret source <ExternalLink size={12} aria-hidden="true" />
            </a>
          ) : null}
        </>
      ) : null}

      {d.news.length > 0 || d.social.length > 0 || (d.jobs ?? []).length > 0 ? (
        <>
          <h2 className="mt-8 mb-2 text-[13px] font-semibold tracking-wide text-muted uppercase">Web presence</h2>
          <ul className="grid gap-2 text-[14px]">
            {d.social.map((s) => (
              <li key={s.url}><a className="text-accent hover:underline" href={s.url} target="_blank" rel="noopener noreferrer">{s.platform}</a></li>
            ))}
            {d.news.map((n) => (
              <li key={n.url}><a className="text-accent hover:underline" href={n.url} target="_blank" rel="noopener noreferrer">{n.title}</a> <span className="text-muted">· {formatDate(n.at)}</span></li>
            ))}
          </ul>
        </>
      ) : null}

      {(d.jobs ?? []).length > 0 ? (
        <>
          <h2 className="mt-8 mb-2 text-[13px] font-semibold tracking-wide text-muted uppercase">Open roles on the company site</h2>
          <ul className="grid gap-2 text-[14px]">
            {(d.jobs ?? []).map((j) => (
              <li key={j.url}>
                <a className="text-accent hover:underline" href={j.url} target="_blank" rel="noopener noreferrer">{j.title}</a>
                {j.at ? <span className="text-muted"> · posted {formatDate(j.at)}</span> : <span className="text-muted"> · open posting</span>}
              </li>
            ))}
          </ul>
        </>
      ) : null}

      {Object.keys(d.missing).length > 0 ? (
        <>
          <h2 className="mt-8 mb-2 text-[13px] font-semibold tracking-wide text-muted uppercase">Not published (never estimated)</h2>
          <ul className="grid gap-1.5 rounded-panel border border-line bg-paper p-4 text-[13px] text-graphite">
            {Object.entries(d.missing).map(([k, why]) => (
              <li key={k}><span className="font-medium text-ink">{k.replace(/_/g, ' ')}:</span> {why}</li>
            ))}
          </ul>
        </>
      ) : null}

      {d.hash ? <p className="mt-8 text-[11.5px] break-all text-faint">Registry hash {d.hash}</p> : null}
    </>
  )
}

function ComparePage({ a, b }: { a: string; b: string }) {
  const sa = useDoc(a)
  const sb = useDoc(b)
  if (!sa || !sb) return <Loading />
  if (!sa.doc || !sb.doc) return <NotFound message={sa.error ?? sb.error} />
  const x = sa.doc
  const y = sb.doc
  const keys: string[] = []
  ;[...x.facts, ...y.facts].forEach((f) => {
    if (!keys.includes(f.k)) keys.push(f.k)
  })
  const find = (d: ExDoc, k: string) => d.facts.find((f) => f.k === k)
  const cell = (d: ExDoc, f?: ExFact) => (
    <div className="min-w-0">
      <p className="text-[11.5px] font-medium text-muted sm:hidden">{d.name}</p>
      {f ? (
        <>
          <p className="text-[14.5px] leading-snug font-medium [overflow-wrap:anywhere]">{f.v || '—'}</p>
          <SourceLine fact={f} base={d.base} />
        </>
      ) : (
        <p className="text-[13px] text-muted italic">Not available</p>
      )}
    </div>
  )
  const label = (k: string) => find(x, k)?.l ?? find(y, k)?.l ?? k

  return (
    <>
      <a href="#/explore" className="inline-flex min-h-10 items-center gap-1.5 text-[13px] text-muted hover:text-ink">
        <ArrowLeft size={14} aria-hidden="true" /> All companies
      </a>
      <h1 className="mt-2 mb-5 text-[clamp(1.4rem,4vw,2rem)] leading-tight font-semibold tracking-[-0.03em]">Compare</h1>
      <div className="hidden gap-4 px-4 pb-2 text-[13px] font-semibold sm:grid sm:grid-cols-[170px_1fr_1fr]">
        <span />
        <a className="text-accent hover:underline" href={`#/explore/c/${x.n}`}>{x.name}</a>
        <a className="text-accent hover:underline" href={`#/explore/c/${y.n}`}>{y.name}</a>
      </div>
      <ul className="overflow-hidden rounded-panel border border-line bg-paper">
        {keys.map((k) => {
          const fa = find(x, k)
          const fb = find(y, k)
          const differ = (fa?.v ?? '') !== (fb?.v ?? '')
          return (
            <li
              key={k}
              className={cn(
                'grid gap-2 border-b border-line px-4 py-3.5 last:border-b-0 sm:grid-cols-[170px_1fr_1fr] sm:gap-4',
                differ && 'bg-warning-soft/60',
              )}
            >
              <p className="text-[12px] font-medium tracking-wide text-muted uppercase">{label(k)}</p>
              {cell(x, fa)}
              {cell(y, fb)}
            </li>
          )
        })}
      </ul>
      <p className="mt-3 text-[12.5px] text-muted">Highlighted rows differ. Every value links to its source.</p>
    </>
  )
}

function Loading({ label }: { label?: string }) {
  return (
    <p className="flex items-center gap-2 py-10 text-[14px] text-muted" role="status">
      <LoaderCircle size={16} className="animate-spin" aria-hidden="true" /> {label ?? 'Loading…'}
    </p>
  )
}

function NotFound({ message }: { message?: string }) {
  return (
    <div className="py-10">
      <h1 className="text-xl font-semibold">Company not found</h1>
      <p className="mt-2 text-[14px] text-graphite">{message ?? 'It is not in this dataset.'}</p>
      <a href="#/explore" className="mt-4 inline-block text-accent hover:underline">Back to search</a>
    </div>
  )
}

function About({ index }: { index: IndexRow[] | null }) {
  const section = 'mt-8'
  const h2 = 'mb-2 text-[13px] font-semibold tracking-wide text-muted uppercase'
  const p = 'text-[14px] leading-relaxed text-graphite'
  return (
    <>
      <a href="#/explore" className="inline-flex min-h-10 items-center gap-1.5 text-[13px] text-muted hover:text-ink">
        <ArrowLeft size={14} aria-hidden="true" /> All companies
      </a>
      <h1 className="mt-2 text-[clamp(1.6rem,4.5vw,2.25rem)] leading-tight font-semibold tracking-[-0.03em]">How this works</h1>
      <p className="mt-3 text-[15px] leading-relaxed text-graphite">
        A source-backed company explorer for Norway. Every fact is shown with the field it came from, the URL it was read
        from, the time it was retrieved and a SHA-256 of the value.
      </p>

      <section className={section}>
        <h2 className={h2}>Where the facts come from</h2>
        <ul className="grid gap-1.5 text-[14px] leading-relaxed text-graphite">
          <li>
            <span className="font-medium text-ink">Enhetsregisteret</span> — legal name, organisation form, address,
            founding date, employees, industry, status and the website the company registered.
          </li>
          <li>
            <span className="font-medium text-ink">Regnskapsregisteret</span> — the filed annual accounts, when the company
            has filed them.
          </li>
          <li>
            <span className="font-medium text-ink">The company’s own website</span> — only after the site proves it belongs
            to this company: its domain must match the registered name <em>and</em> the page must carry the organisation
            number or the exact legal name. A parent-group or sister-company site fails that check and is reported as not
            verified, never published.
          </li>
          <li>
            <span className="font-medium text-ink">Recognised job boards</span> — postings linked from the verified site,
            including Teamtailor, Recruitee, Webcruiter, Jobbnorge, EasyCruit and FINN, the employer’s own Workday tenant
            (read from its public job feed) and its SuccessFactors career site (read from the country search that site
            renders), plus the group’s shared careers page when the company’s own host sends visitors there. A vacancy on a shared page counts only when its card names a Norwegian unit of the group (“Telenor
            Norge”, not “Telenor Danmark”), and the item states the hiring unit.
          </li>
        </ul>
      </section>

      <section className={section}>
        <h2 className={h2}>Coverage</h2>
        <p className={p}>
          The crawled dataset holds {index ? index.length.toLocaleString('en-GB') : 'the'} company profiles. Anything outside
          it is still findable: a search that misses the dataset asks Enhetsregisteret live and shows a registry-only
          record, clearly labelled, instead of claiming the company does not exist.
        </p>
      </section>

      <section className={section}>
        <h2 className={h2}>What is never shown</h2>
        <p className={p}>
          No estimates, no inferred revenue, no unverified website, no group-level substitute. When a field cannot be
          sourced, the profile lists it under “Not published (never estimated)” with the reason.
        </p>
      </section>

      <section className={section}>
        <h2 className={h2}>Known limits</h2>
        <ul className="grid gap-1.5 text-[14px] leading-relaxed text-graphite">
          <li>Jobbnorge and Workday are read from the public feeds their pages call, not from the page, and a Workday tenant
            or SuccessFactors career site is only read when the company’s own site links it and its host carries the
            company’s name. Employers whose vacancies live only in an ATS that renders solely in the browser, or whose
            careers site answers with a maintenance page, still show no postings. Only postings in Norway are published.</li>
          <li>Companies that registered no website, or whose site is unreachable, show no website-derived facts.</li>
          <li>News rendered client-side is not read; only server-rendered posts with a real publish date are published.</li>
        </ul>
      </section>

      <section className={section}>
        <h2 className={h2}>Check it yourself</h2>
        <p className={p}>
          Every fact has “Check source”, which re-fetches the source in your browser and compares it with the stored value
          and hash. Company pages also export every sourced fact as CSV or the full profile as JSON.
        </p>
      </section>
    </>
  )
}

export function Explorer() {
  const [route, setRoute] = useState<Route>(parseRoute)
  const [index, setIndex] = useState<IndexRow[] | null>(null)
  const [picked, setPicked] = useState<string[]>([])
  const names = useRef<Record<string, string>>({})

  useEffect(() => {
    const onHash = () => setRoute(parseRoute())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    loadIndex()
      .then((rows) => {
        rows.forEach((r) => {
          names.current[r[0]] = r[1]
        })
        setIndex(rows)
      })
      .catch(() => setIndex([]))
  }, [])

  function toggle(org: string) {
    setPicked((cur) => (cur.includes(org) ? cur.filter((o) => o !== org) : [...cur, org].slice(-2)))
  }

  return (
    <Shell wide={route.page === 'compare'}>
      {route.page === 'home' ? <Home index={index} picked={picked} toggle={toggle} /> : null}
      {route.page === 'about' ? <About index={index} /> : null}
      {route.page === 'company' ? <CompanyPage org={route.org} picked={picked} toggle={toggle} /> : null}
      {route.page === 'compare' ? <ComparePage a={route.a} b={route.b} /> : null}
      <CompareBar picked={picked} names={names.current} clear={() => setPicked([])} />
    </Shell>
  )
}
