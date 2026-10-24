import { Database, Fingerprint, Landmark, Lock, ShieldCheck, Workflow } from 'lucide-react'
import { Reveal } from '../ui'

const pillars = [
  { icon: Landmark, label: 'Brønnøysund Register Centre' },
  { icon: Lock, label: 'Google & GitHub SSO' },
  { icon: Database, label: 'PostgreSQL audit store' },
  { icon: Fingerprint, label: 'SHA-256 evidence hashing' },
  { icon: ShieldCheck, label: 'Guard-railed agent runs' },
  { icon: Workflow, label: 'Spring Boot + Python agent' },
]

export function TrustStrip() {
  return (
    <section className="border-b border-line bg-canvas" aria-label="Platform assurances">
      <div className="page-shell flex flex-col gap-5 py-6 lg:flex-row lg:items-center lg:justify-between lg:gap-10">
        <Reveal>
          <p className="text-[11px] font-medium tracking-[0.16em] text-faint uppercase">
            Built on verifiable infrastructure
          </p>
        </Reveal>
        <Reveal delay={80}>
          <ul className="flex flex-wrap items-center gap-x-7 gap-y-3">
            {pillars.map((pillar) => (
              <li
                key={pillar.label}
                className="flex items-center gap-2 text-[13px] whitespace-nowrap text-graphite"
              >
                <pillar.icon size={15} className="text-faint" aria-hidden="true" />
                {pillar.label}
              </li>
            ))}
          </ul>
        </Reveal>
      </div>
    </section>
  )
}