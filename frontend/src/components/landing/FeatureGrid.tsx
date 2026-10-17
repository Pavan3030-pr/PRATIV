import type { LucideIcon } from 'lucide-react'
import { Fingerprint, Landmark, ShieldCheck, Waypoints } from 'lucide-react'
import { Card, Reveal } from '../ui'

const features: { index: string; icon: LucideIcon; title: string; copy: string; points: string[] }[] = [
  {
    index: '01',
    icon: Landmark,
    title: 'Registry verification',
    copy: 'Identity starts at the source — the Norwegian Central Coordinating Register, not a scraped copy of it.',
    points: ['Live Brreg lookups', 'Official legal names & addresses', 'Incorporation dates'],
  },
  {
    index: '02',
    icon: Fingerprint,
    title: 'Deterministic evidence',
    copy: 'Every stored record carries a content hash, so proof of what was true yesterday still holds today.',
    points: ['SHA-256 delta syncs', 'Source URLs & snippets', 'Crawl timestamps'],
  },
  {
    index: '03',
    icon: Waypoints,
    title: 'Semantic lineage',
    copy: 'Embeddings connect each derived claim to the evidence behind it, so relationships stay auditable.',
    points: ['pgvector embeddings', 'Metric-level proof checks', 'Traceable derivation'],
  },
  {
    index: '04',
    icon: ShieldCheck,
    title: 'Guard-railed agents',
    copy: 'Agentic workflows run inside hard limits — capped, logged, and denied anything they cannot source.',
    points: ['Request budgets', 'Persisted run traces', 'Withheld without proof'],
  },
]

export function FeatureGrid() {
  return (
    <section id="platform" className="border-b border-line bg-canvas">
      <div className="page-shell py-20 lg:py-28">
        <Reveal className="max-w-2xl">
          <p className="kicker">The platform</p>
          <h2 className="mt-5 text-[clamp(1.9rem,3.6vw,2.75rem)] leading-[1.08] font-semibold tracking-[-0.035em] text-ink">
            Everything a verification team needs. Nothing it doesn't.
          </h2>
        </Reveal>

        <div className="mt-12 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {features.map((feature, index) => (
            <Reveal key={feature.title} delay={index * 70}>
              <Card interactive className="flex h-full flex-col">
                <div className="flex items-center justify-between">
                  <span className="grid size-10 place-items-center rounded-panel border border-line bg-sunken">
                    <feature.icon size={17} className="text-ink" aria-hidden="true" />
                  </span>
                  <span className="mono-data text-[11px] text-faint">{feature.index}</span>
                </div>

                <h3 className="mt-5 text-[17px] font-semibold tracking-[-0.02em] text-ink">
                  {feature.title}
                </h3>
                <p className="mt-2.5 text-[14px] leading-[1.6] text-graphite">{feature.copy}</p>

                <ul className="mt-5 space-y-2 border-t border-line pt-4">
                  {feature.points.map((point) => (
                    <li key={point} className="flex items-center gap-2 text-[13px] text-muted">
                      <span
                        className="size-1 rounded-full bg-accent/60"
                        aria-hidden="true"
                      />
                      {point}
                    </li>
                  ))}
                </ul>
              </Card>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}