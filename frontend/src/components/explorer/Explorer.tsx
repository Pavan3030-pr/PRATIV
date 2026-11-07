import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowLeft,
  Check,
  ChevronDown,
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
  loadDoc,
  loadIndex,
  money,
  sourceLabel,
  type CheckResult,
  type ExDoc,
  type ExFact,
  type IndexRow,
} from '../../lib/explorerData'

type Route =
  | { page: 'home' }
  | { page: 'company'; org: string }
  | { page: 'compare'; a: string; b: string }

function parseRoute(): Route {
  const parts = window.location.hash.replace(/^#\/?/, '').split('/').filter(Boolean)
  if (parts[1] === 'c' && /^\d{9}$/.test(parts[2] ?? '')) return { page: 'company', org: parts[2] }
  if (parts[1] === 'compare' && /^\d{9}$/.test(parts[2] ?? '') && /^\d{9}$/.test(parts[3] ?? '')) {
    return { page: 'compare', a: parts[2], b: parts[3] }
  }
  return { page: 'home' }
}

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
          <a href="#" className="text-[13px] text-muted hover:text-ink">
            About
          </a>
        </div>
      </header>
      <main className={cn('mx-auto px-4 py-6 sm:py-10', wide ? 'max-w-5xl' : 'max-w-3xl')}>{children}</main>
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
      aria-label={on ? 'Remove from comparison' : 'Add to comparison'}
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

function Home({ index, picked, toggle }: { index: IndexRow[] | null; picked: string[]; toggle: (o: string) => void }) {
  const [q, setQ] = useState('')
  const [onlyAccounts, setOnlyAccounts] = useState(false)
  const [onlyWeb, setOnlyWeb] = useState(false)
  const [limit, setLimit] = useState(30)

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
    return first
      ? out.sort((a, b) => Number(b[1].toLowerCase().startsWith(first)) - Number(a[1].toLowerCase().startsWith(first)))
      : out
  }, [index, hay, q, onlyAccounts, onlyWeb])

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
            <p className="mt-6 text-[14px] text-graphite">No match. Try fewer words, or a 9-digit organisation number.</p>
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
  if (!state) return <Loading />
  if (state.error || !state.doc) return <NotFound message={state.error} />
  const d = state.doc
  const active = (d.facts.find((f) => f.k === 'company_status')?.v ?? '').toLowerCase().startsWith('active')
  const retrieved = d.facts[0]?.t

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
        {d.update.status ? (
          <Badge tone={d.update.status === 'changed' ? 'warning' : 'neutral'}>Update: {d.update.status}</Badge>
        ) : null}
      </div>
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
      </div>

      {d.summary ? <p className="mt-5 rounded-panel border border-line bg-paper p-4 text-[14px] leading-relaxed text-graphite">{d.summary}</p> : null}

      <h2 className="mt-8 mb-2 text-[13px] font-semibold tracking-wide text-muted uppercase">Facts and their sources</h2>
      <ul className="overflow-hidden rounded-panel border border-line bg-paper">
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

      {d.news.length > 0 || d.social.length > 0 ? (
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

      <p className="mt-8 text-[11.5px] break-all text-faint">Registry hash {d.hash}</p>
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

function Loading() {
  return (
    <p className="flex items-center gap-2 py-10 text-[14px] text-muted" role="status">
      <LoaderCircle size={16} className="animate-spin" aria-hidden="true" /> Loading…
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
      {route.page === 'company' ? <CompanyPage org={route.org} picked={picked} toggle={toggle} /> : null}
      {route.page === 'compare' ? <ComparePage a={route.a} b={route.b} /> : null}
      <CompareBar picked={picked} names={names.current} clear={() => setPicked([])} />
    </Shell>
  )
}
