import { ArrowRight, BadgeCheck, Check, Landmark, ShieldCheck, Waypoints } from 'lucide-react'
import { Badge, Button } from '../ui'

const assurances = [
  'Official Brreg registry data',
  'Deterministic evidence hashing',
  'Google & GitHub sign-in',
]

const pathSteps = [
  { label: 'Registry fetch', state: 'RECEIVED', tone: 'text-accent' },
  { label: 'Evidence hashed', state: 'SHA-256', tone: 'text-accent' },
  { label: 'Evidence stored', state: 'PERSISTED', tone: 'text-success' },
]

export function Hero({ onStart }: { onStart: () => void }) {
  return (
    <section id="top" className="relative overflow-hidden border-b border-line bg-paper">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-40 right-[-12%] size-[560px] rounded-full bg-accent/[0.06] blur-3xl"
      />

      <div className="page-shell relative grid items-center gap-14 py-16 lg:grid-cols-[1.02fr_0.98fr] lg:gap-16 lg:py-24">
        <div style={{ animation: 'rise-in 0.7s cubic-bezier(0.22, 1, 0.36, 1) both' }}>
          <p className="kicker text-accent">
            Verify the vector · Validate the source · Anchor the data
          </p>

          <h1 className="mt-6 text-[clamp(2.5rem,5.6vw,4rem)] leading-[1.03] font-semibold tracking-[-0.04em] text-ink">
            Company intelligence with a chain of custody.
          </h1>

          <p className="mt-6 max-w-xl text-[17px] leading-[1.65] text-graphite">
            SIGNALPOST verifies every organization against Norway's Brønnøysund Register Centre,
            stores source-backed evidence for each field, and audits the semantic lineage behind
            it — for teams that cannot afford unverified facts.
          </p>

          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Button size="lg" onClick={onStart} icon={<ArrowRight size={16} />}>
              Start researching
            </Button>
            <Button size="lg" variant="secondary" onClick={onStart}>
              Sign in to workspace
            </Button>
          </div>

          <ul className="mt-9 flex flex-wrap items-center gap-x-6 gap-y-2.5">
            {assurances.map((item) => (
              <li key={item} className="flex items-center gap-2 text-[13px] text-muted">
                <Check size={14} className="text-success" aria-hidden="true" />
                {item}
              </li>
            ))}
          </ul>
        </div>

        <div
          className="relative"
          style={{ animation: 'rise-in 0.7s cubic-bezier(0.22, 1, 0.36, 1) 0.12s both' }}
        >
          <div className="rounded-card border border-line bg-paper p-5 shadow-lift sm:p-6">
            <div className="flex items-start justify-between gap-4 border-b border-line pb-4">
              <div className="flex items-center gap-3">
                <span className="grid size-10 place-items-center rounded-panel border border-line bg-sunken">
                  <Landmark size={17} className="text-graphite" aria-hidden="true" />
                </span>
                <span>
                  <span className="block text-[13px] font-semibold text-ink">
                    Enhetsregisteret record
                  </span>
                  <span className="block text-[11px] text-faint">
                    Brønnøysund Register Centre
                  </span>
                </span>
              </div>
              <Badge tone="success" icon={<BadgeCheck size={13} aria-hidden="true" />}>
                Verified
              </Badge>
            </div>

            <dl className="grid grid-cols-2 gap-x-4 gap-y-4 py-5">
              <div>
                <dt className="text-[11px] tracking-[0.06em] text-faint uppercase">
                  Organization number
                </dt>
                <dd className="mono-data mt-1.5 text-sm font-medium text-ink">923609016</dd>
              </div>
              <div>
                <dt className="text-[11px] tracking-[0.06em] text-faint uppercase">Legal name</dt>
                <dd className="mt-1.5 text-sm font-medium text-ink">Equinor ASA</dd>
              </div>
              <div className="col-span-2">
                <dt className="text-[11px] tracking-[0.06em] text-faint uppercase">
                  Registered address
                </dt>
                <dd className="mt-1.5 text-sm text-graphite">Stavanger, Norway</dd>
              </div>
            </dl>

            <div className="flex items-center justify-between gap-2 border-t border-line py-3">
              {pathSteps.map((step, index) => (
                <div key={step.label} className="flex min-w-0 flex-1 items-center gap-2">
                  {index > 0 ? <span className="h-px w-3 bg-line-strong" aria-hidden="true" /> : null}
                  <span className="min-w-0">
                    <span className="block truncate text-[12px] font-medium text-ink">
                      {step.label}
                    </span>
                    <span className={`mono-data block text-[10px] ${step.tone}`}>{step.state}</span>
                  </span>
                </div>
              ))}
            </div>

            <div className="rounded-panel border border-line bg-canvas p-4">
              <div className="flex items-center justify-between gap-3">
                <span className="kicker text-[10px] text-accent">financial_revenue</span>
                <span className="mono-data text-[11px] text-faint">18 Dec 2025</span>
              </div>
              <p className="mt-2 text-[13px] leading-[1.55] text-graphite">
                Withheld — no metric-level evidence row cites this field yet.
              </p>
            </div>
          </div>

          <div className="absolute -bottom-6 -left-4 hidden items-center gap-2 rounded-full border border-line bg-paper px-4 py-2 shadow-lift sm:flex">
            <ShieldCheck size={14} className="text-success" aria-hidden="true" />
            <span className="mono-data text-[11px] text-graphite">sha256:3f9a…c214</span>
          </div>

          <div className="absolute -top-5 right-3 hidden items-center gap-2 rounded-full border border-accent/15 bg-accent-soft px-3.5 py-1.5 sm:flex">
            <Waypoints size={13} className="text-accent" aria-hidden="true" />
            <span className="text-[11px] font-medium text-accent">Lineage traced</span>
          </div>
        </div>
      </div>
    </section>
  )
}