import { Fingerprint, ScrollText, ShieldCheck, Waypoints } from 'lucide-react'
import { Reveal } from '../ui'

const anchors = [
  {
    icon: Fingerprint,
    title: 'Deterministic hashing',
    copy: 'Identical input, identical hash — every time, on any machine.',
  },
  {
    icon: Waypoints,
    title: 'Vector lineage',
    copy: 'Embeddings connect each derived claim to the evidence behind it.',
  },
  {
    icon: ShieldCheck,
    title: 'Guardrail budget',
    copy: 'Outbound agent calls are counted, capped, and written to the audit log.',
  },
  {
    icon: ScrollText,
    title: 'Audit-ready export',
    copy: 'Take the whole workspace out as CSV whenever a review asks for it.',
  },
]

const recordLines = [
  { key: 'company_number', value: '"923609016"' },
  { key: 'target_metric_key', value: '"financial_revenue"' },
  { key: 'source_url_link', value: '"data.brreg.no/enhetsregisteret/…"' },
  { key: 'delta_sync_hash', value: '"sha256:3f9a…c214"' },
  { key: 'vector_lineage', value: 'pgvector · indexed' },
  { key: 'guardrail_status', value: 'capped · audited' },
]

export function Architecture() {
  return (
    <section id="architecture" className="bg-ink text-white">
      <div className="page-shell grid gap-12 py-20 lg:grid-cols-[1fr_1fr] lg:gap-16 lg:py-28">
        <Reveal>
          <p className="kicker text-white/45">Why SIGNALPOST</p>
          <h2 className="mt-5 text-[clamp(1.9rem,3.6vw,2.75rem)] leading-[1.08] font-semibold tracking-[-0.035em] text-white">
            Anchored by design.
          </h2>
          <p className="mt-5 max-w-lg text-[16px] leading-[1.7] text-white/60">
            Verification is not a feature bolted on at the end. Hashing, embeddings, and agent
            limits are part of how a record is written, which means the audit trail exists before
            anyone asks for one.
          </p>

          <dl className="mt-10 grid gap-x-8 gap-y-7 sm:grid-cols-2">
            {anchors.map((anchor) => (
              <div key={anchor.title}>
                <dt className="flex items-center gap-2.5 text-[14px] font-medium text-white">
                  <anchor.icon size={16} className="text-indigo-300" aria-hidden="true" />
                  {anchor.title}
                </dt>
                <dd className="mt-1.5 text-[13px] leading-[1.6] text-white/50">{anchor.copy}</dd>
              </div>
            ))}
          </dl>
        </Reveal>

        <Reveal delay={110}>
          <div className="rounded-card border border-white/10 bg-white/[0.04] p-5 sm:p-6">
            <div className="flex items-center justify-between border-b border-white/10 pb-4">
              <span className="text-[13px] font-medium text-white/80">Stored evidence record</span>
              <span className="mono-data rounded-full border border-white/10 px-2.5 py-0.5 text-[10px] text-white/45">
                PostgreSQL
              </span>
            </div>
            <dl className="mt-4 space-y-3">
              {recordLines.map((line) => (
                <div
                  key={line.key}
                  className="flex items-baseline justify-between gap-4 border-b border-dashed border-white/[0.07] pb-3 last:border-0 last:pb-0"
                >
                  <dt className="mono-data text-[12px] text-indigo-300/90">{line.key}</dt>
                  <dd className="mono-data text-right text-[12px] break-all text-white/70">
                    {line.value}
                  </dd>
                </div>
              ))}
            </dl>
            <p className="mt-5 text-[12px] leading-[1.6] text-white/40">
              Values without a matching evidence row are withheld from the interface rather than
              estimated.
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  )
}