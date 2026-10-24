import { useState } from 'react'
import { ArrowUpRight, BadgeCheck, CircleAlert, Database, Check, Copy, Download, ExternalLink, FileSearch, Globe, Info } from 'lucide-react'
import { formatDate, hasMetricEvidence, normalizedName } from '../../lib/api'
import type { AgentCrawl, Company, Evidence } from '../../types'

type LineageDetailProps = {
  company: Company
  crawl?: AgentCrawl
}

function evidenceDate(evidence: Evidence) {
  return evidence.crawl_timestamp || evidence.recorded_at
}

function SectionTitle({ title, meta }: { title: string; meta?: string }) {
  return (
    <div className="mb-3 flex items-baseline justify-between gap-3">
      <h3 className="text-[13px] font-semibold tracking-[-0.01em] text-ink">{title}</h3>
      {meta ? <span className="text-[12px] text-faint">{meta}</span> : null}
    </div>
  )
}

const money = (value: number | null | undefined, currency = 'NOK') =>
  value === null || value === undefined ? 'Not reported' : `${currency} ${value.toLocaleString('en-GB').replaceAll(',', ' ')}`

function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      aria-label={copied ? `${label} copied` : `Copy ${label}`}
      onClick={() => {
        navigator.clipboard?.writeText(value).then(
          () => {
            setCopied(true)
            window.setTimeout(() => setCopied(false), 1500)
          },
          () => undefined,
        )
      }}
      className="inline-flex size-7 shrink-0 items-center justify-center rounded-control border border-line text-graphite hover:bg-sunken"
    >
      {copied ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}
    </button>
  )
}

const safeHref = (url?: string | null) => (url && /^https?:\/\//i.test(url) ? url : undefined)

function downloadAuditTrail(company: Company, crawl: AgentCrawl | undefined, evidences: Evidence[]) {
  const payload = {
    exported_at: new Date().toISOString(),
    note: 'Every value below is copied from its source record; nothing is estimated. Verify with source_url_link and delta_sync_hash.',
    company_number: company.company_number,
    legal_name: normalizedName(company),
    delta_sync_hash: company.delta_sync_hash ?? crawl?.delta_sync_hash ?? null,
    content_hash: crawl?.content_hash ?? null,
    profile: company,
    evidences,
    agent_crawl: crawl ?? null,
  }
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `signalpost-audit-${company.company_number}.json`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export function LineageDetail({ company, crawl }: LineageDetailProps) {
  const evidences = Array.from(
    new Map(
      (company.lineage_evidences ?? []).map((evidence) => [
        `${evidence.target_metric_key}|${evidence.extracted_text_snippet}|${evidence.source_url_link}`,
        evidence,
      ]),
    ).values(),
  )
  const registryBacked = evidences.some(
    (evidence) =>
      evidence.target_metric_key?.toLowerCase().includes('legal') ||
      evidence.target_metric_key?.toLowerCase().includes('registry'),
  )
  const revenueVerified = hasMetricEvidence(company, 'financial_revenue')
  const profitVerified = hasMetricEvidence(company, 'net_profit')

  const pathSteps = [
    {
      icon: FileSearch,
      title: 'Public registry request',
      meta: 'Norwegian Enhetsregisteret · company identity',
      state: 'RECEIVED',
      done: true,
    },
    {
      icon: ArrowUpRight,
      title: 'Python discovery agent',
      meta: crawl ? 'Crawl completed for this lookup' : 'No agent crawl attached to this record',
      state: crawl ? 'RAN' : 'NOT RUN',
      done: Boolean(crawl),
    },
    {
      icon: Database,
      title: 'Spring Boot audit store',
      meta: 'PostgreSQL profile + vector-ready schema',
      state: 'PERSISTED',
      done: true,
    },
  ]

  return (
    <div className="space-y-7">
      <section>
        <div className="rounded-card border border-line bg-paper p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="mono-data grid size-11 shrink-0 place-items-center rounded-panel border border-line bg-sunken text-[15px] font-semibold text-ink">
                {normalizedName(company).slice(0, 1)}
              </span>
              <span>
                <span className="block text-[15px] font-semibold tracking-[-0.02em] text-ink">
                  {normalizedName(company)}
                </span>
                <span className="mono-data mt-1 flex items-center gap-2 text-[12px] text-graphite">
                  {company.company_number}
                  <CopyButton value={company.company_number} label="organisation number" />
                </span>
              </span>
            </div>
            <span className="inline-flex items-center gap-1.5 text-[12px] font-medium text-success">
              <BadgeCheck size={14} aria-hidden="true" />
              Registry record
            </span>
          </div>
          <button
            type="button"
            onClick={() => downloadAuditTrail(company, crawl, evidences)}
            className="mt-4 inline-flex h-9 items-center gap-2 rounded-control border border-line-strong bg-paper px-3.5 text-[13px] font-medium text-ink transition-colors duration-200 hover:bg-sunken"
          >
            <Download size={14} aria-hidden="true" />
            Export audit trail (JSON)
          </button>

          <dl className="mt-5 grid gap-4 border-t border-line pt-4 sm:grid-cols-[1.5fr_1fr]">
            <div>
              <dt className="text-[11px] tracking-[0.08em] text-faint uppercase">
                Registered address
              </dt>
              <dd className="mt-1 text-[13px] leading-[1.55] text-graphite">
                {company.registered_address || crawl?.registered_address || 'Not returned by registry'}
              </dd>
            </div>
            <div>
              <dt className="text-[11px] tracking-[0.08em] text-faint uppercase">
                Incorporation date
              </dt>
              <dd className="mt-1 text-[13px] leading-[1.55] text-graphite">
                {formatDate(company.incorporation_date || crawl?.incorporation_date)}
              </dd>
            </div>
          </dl>
        </div>
      </section>

      <section>
        <SectionTitle title="Processing path" meta={`${evidences.length} stored records`} />
        <div className="rounded-card border border-line bg-canvas p-4">
          {pathSteps.map((step, index) => (
            <div key={step.title}>
              <div className="grid grid-cols-[30px_1fr_auto] items-center gap-3">
                <span className="grid size-7 place-items-center rounded-control border border-line bg-paper">
                  <step.icon size={14} className="text-graphite" aria-hidden="true" />
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-[13px] font-medium text-ink">{step.title}</span>
                  <span className="block truncate text-[12px] text-muted">{step.meta}</span>
                </span>
                <span
                  className={`mono-data text-[10px] font-semibold ${step.done ? 'text-success' : 'text-faint'}`}
                >
                  {step.state}
                </span>
              </div>
              {index < pathSteps.length - 1 ? (
                <span className="my-1.5 ml-3.5 h-3 w-px bg-line-strong" aria-hidden="true" />
              ) : null}
            </div>
          ))}
        </div>
      </section>

      <section>
        <SectionTitle title="Source evidence" meta="Captured by backend" />
        {evidences.length === 0 ? (
          <div className="flex items-start gap-3 rounded-card border border-warning/20 bg-warning-soft p-4">
            <CircleAlert size={16} className="mt-0.5 shrink-0 text-warning" aria-hidden="true" />
            <p className="text-[13px] leading-[1.6] text-warning">
              No evidence rows are attached to this profile yet.
            </p>
          </div>
        ) : (
          <ul className="space-y-3">
            {evidences.map((evidence, index) => (
              <li
                key={evidence.evidence_id || `${evidence.target_metric_key}-${index}`}
                className="rounded-card border border-line bg-paper p-4"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="kicker text-[10px] text-accent">
                    {(evidence.target_metric_key || 'source record').replaceAll('_', ' ')}
                  </span>
                  <span className="mono-data text-[11px] text-faint">
                    {formatDate(evidenceDate(evidence))}
                  </span>
                </div>
                <p className="mt-2.5 text-[13px] leading-[1.6] text-graphite">
                  {evidence.extracted_text_snippet ||
                    evidence.explanation_chain ||
                    'Registry evidence was recorded.'}
                </p>
                {safeHref(evidence.source_url_link) ? (
                  <a
                    href={evidence.source_url_link}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2.5 inline-flex items-center gap-1.5 text-[13px] font-medium text-accent transition-opacity duration-200 hover:opacity-75"
                  >
                    Open source
                    <ExternalLink size={13} aria-hidden="true" />
                  </a>
                ) : null}
              </li>
            ))}
          </ul>
        )}
        {!registryBacked ? (
          <div className="mt-3 flex items-start gap-2.5 rounded-card border border-line bg-canvas p-3.5">
            <CircleAlert size={15} className="mt-0.5 shrink-0 text-muted" aria-hidden="true" />
            <p className="text-[12px] leading-[1.6] text-muted">
              The stored evidence does not independently verify every profile field.
            </p>
          </div>
        ) : null}
      </section>

      {(company.delta_sync_hash || crawl?.delta_sync_hash) ? (
        <section>
          <SectionTitle title="Update fingerprint" meta="SHA-256" />
          <div className="rounded-card border border-line bg-paper p-4">
            <div className="flex items-start justify-between gap-3">
              <code className="mono-data block min-w-0 break-all text-[12px] leading-[1.6] text-ink">
                {company.delta_sync_hash ?? crawl?.delta_sync_hash}
              </code>
              <CopyButton value={(company.delta_sync_hash ?? crawl?.delta_sync_hash) as string} label="SHA-256 hash" />
            </div>
            <details className="group mt-3">
              <summary className="inline-flex cursor-pointer items-center gap-1.5 text-[12px] font-medium text-accent">
                <Info size={13} aria-hidden="true" />
                What is this hash?
              </summary>
              <p className="mt-2 text-[12px] leading-[1.65] text-muted">
                A SHA-256 fingerprint of the seven core registry fields (organisation number, name, form, founding
                date, employees, industry, address) in a fixed order. On the next lookup the same fields are hashed
                again: an identical hash means unchanged, a different hash means the registry changed and the
                changed fields are listed. Anyone can recompute it from the cited source.
              </p>
            </details>
          </div>
        </section>
      ) : null}

      {crawl?.website ? (
        <section>
          <SectionTitle title="Web presence" meta={crawl.website.verified ? 'Ownership verified' : 'Not verified'} />
          <div className="space-y-3 rounded-card border border-line bg-paper p-4">
            <p className="flex items-start gap-2 text-[13px] leading-[1.6] text-graphite">
              <Globe size={15} className="mt-0.5 shrink-0 text-muted" aria-hidden="true" />
              {crawl.website.verified && safeHref(crawl.website.url) ? (
                <span className="min-w-0 break-all">
                  <a href={safeHref(crawl.website.url)} target="_blank" rel="noreferrer" className="font-medium text-accent hover:opacity-75">
                    {crawl.website.url}
                  </a>{' '}
                  shows this company&apos;s {crawl.website.verified_by?.replaceAll('_', ' ')}.
                </span>
              ) : (
                <span>{crawl.website.reason || 'The registry lists no website for this company.'}</span>
              )}
            </p>
            {crawl.social_links?.length ? (
              <ul className="flex flex-wrap gap-2" aria-label="Verified social accounts">
                {crawl.social_links.filter((s) => safeHref(s.url)).map((s) => (
                  <li key={s.platform}>
                    <a href={s.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1 text-[12px] text-graphite hover:bg-sunken">
                      {s.platform} · {s.handle}
                      <ExternalLink size={11} aria-hidden="true" />
                    </a>
                  </li>
                ))}
              </ul>
            ) : null}
            {crawl.news?.length ? (
              <ul className="divide-y divide-line border-t border-line">
                {crawl.news.filter((n) => safeHref(n.url)).map((n) => (
                  <li key={n.url} className="py-2.5">
                    <a href={n.url} target="_blank" rel="noreferrer" className="text-[13px] font-medium text-accent hover:opacity-75">
                      {n.title}
                    </a>
                    <span className="mono-data mt-0.5 block text-[11px] text-faint">Published {n.published_at}</span>
                  </li>
                ))}
              </ul>
            ) : crawl.website.verified ? (
              <p className="text-[12px] text-faint">No real, dated news post was found on the verified site.</p>
            ) : null}
          </div>
        </section>
      ) : null}

      {crawl?.financials?.history?.length ? (
        <section>
          <SectionTitle title="Financial history" meta="As filed, newest first" />
          <div className="scroll-area overflow-x-auto rounded-card border border-line bg-paper">
            <table className="w-full min-w-[420px] border-collapse text-left">
              <caption className="sr-only">Annual accounts filed in Regnskapsregisteret</caption>
              <thead>
                <tr className="border-b border-line text-[11px] tracking-[0.08em] text-faint uppercase">
                  <th scope="col" className="px-4 py-2.5 font-medium">Year end</th>
                  <th scope="col" className="px-4 py-2.5 text-right font-medium">Revenue</th>
                  <th scope="col" className="px-4 py-2.5 text-right font-medium">Operating</th>
                  <th scope="col" className="px-4 py-2.5 text-right font-medium">Net result</th>
                </tr>
              </thead>
              <tbody>
                {crawl.financials.history.map((y) => (
                  <tr key={y.period_end} className="border-b border-line last:border-0">
                    <th scope="row" className="mono-data px-4 py-2.5 text-[12px] font-normal text-graphite">{y.period_end}</th>
                    <td className="mono-data px-4 py-2.5 text-right text-[12px] text-ink">{money(y.revenue, y.currency)}</td>
                    <td className="mono-data px-4 py-2.5 text-right text-[12px] text-ink">{money(y.operating_result, y.currency)}</td>
                    <td className="mono-data px-4 py-2.5 text-right text-[12px] text-ink">{money(y.net_result, y.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {safeHref(crawl.financials.source_url) ? (
            <a href={crawl.financials.source_url} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1.5 text-[12px] font-medium text-accent">
              Open filing source <ExternalLink size={12} aria-hidden="true" />
            </a>
          ) : null}
        </section>
      ) : null}

      <section>
        <SectionTitle title="Financial claims" meta="Strict source policy" />
        <dl className="rounded-card border border-line bg-paper">
          <div className="flex items-baseline justify-between gap-4 border-b border-line px-4 py-3.5">
            <dt className="text-[13px] text-muted">Revenue</dt>
            <dd className="mono-data text-right text-[13px] text-ink">
              {revenueVerified ? company.financial_revenue : 'Withheld'}
            </dd>
          </div>
          <div className="flex items-baseline justify-between gap-4 px-4 py-3.5">
            <dt className="text-[13px] text-muted">Net profit</dt>
            <dd className="mono-data text-right text-[13px] text-ink">
              {profitVerified ? company.net_profit : 'Withheld'}
            </dd>
          </div>
        </dl>
        <p className="mt-3 text-[12px] leading-[1.65] text-faint">
          Values without a metric-level evidence row are withheld rather than estimated. Agent
          fallbacks are never treated as verified facts.
        </p>
      </section>

      <section className="flex items-center justify-between gap-3 border-t border-line pt-4">
        <span className="text-[12px] text-faint">Last stored update</span>
        <span className="mono-data text-[12px] text-graphite">
          {formatDate(company.last_modified_timestamp)}
        </span>
      </section>
    </div>
  )
}