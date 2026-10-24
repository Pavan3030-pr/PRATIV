import { ArrowRight } from 'lucide-react'
import { Reveal } from '../ui'

const shifts = [
  {
    problem: 'A revenue figure is pasted into a deck with no record of where it came from.',
    answer: 'Financial values render only when a matching evidence row cites that exact metric.',
  },
  {
    problem: 'An agent answers confidently and leaves no trace of how it reached the answer.',
    answer: 'Guard-railed runs persist their inputs, outputs, and a deterministic delta hash.',
  },
  {
    problem: 'Two systems disagree and nobody can prove which record is authoritative.',
    answer: 'Claim-level lineage links every published fact back to its original source field, hash and timestamp.',
  },
]

export function Narrative() {
  return (
    <section id="verification" className="border-b border-line bg-paper">
      <div className="page-shell py-20 lg:py-28">
        <Reveal className="grid gap-6 lg:grid-cols-[1fr_1fr] lg:gap-16">
          <div>
            <p className="kicker">The problem</p>
            <h2 className="mt-5 text-[clamp(1.9rem,3.6vw,2.75rem)] leading-[1.08] font-semibold tracking-[-0.035em] text-ink">
              Company research fails quietly.
            </h2>
          </div>
          <p className="max-w-xl text-[16px] leading-[1.7] text-graphite lg:pt-9">
            The most dangerous data is the kind that looks finished. Nobody notices a figure has
            no source until it is quoted back in a board meeting. SIGNALPOST makes provenance a
            prerequisite — nothing is displayed unless it can be traced.
          </p>
        </Reveal>

        <div className="mt-14">
          {shifts.map((shift, index) => (
            <Reveal key={shift.problem} delay={index * 70}>
              <div className="grid items-center gap-3 border-t border-line py-7 md:grid-cols-[1fr_auto_1fr] md:gap-8">
                <p className="text-[15px] leading-[1.6] text-muted">{shift.problem}</p>
                <ArrowRight
                  size={16}
                  className="hidden text-faint md:block"
                  aria-hidden="true"
                />
                <p className="text-[15px] leading-[1.6] font-medium text-ink">{shift.answer}</p>
              </div>
            </Reveal>
          ))}
          <div className="border-t border-line" />
        </div>
      </div>
    </section>
  )
}