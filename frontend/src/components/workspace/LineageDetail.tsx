import { ArrowUpRight, BadgeCheck, CircleAlert, Database, ExternalLink, FileSearch } from 'lucide-react'
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
                <span className="mono-data mt-1 block text-[12px] text-graphite">
                  {company.company_number}
                </span>
              </span>
            </div>
            <span className="inline-flex items-center gap-1.5 text-[12px] font-medium text-success">
              <BadgeCheck size={14} aria-hidden="true" />
              Registry record
            </span>
          </div>

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
                {evidence.source_url_link ? (
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