import { Reveal } from '../ui'

const steps = [
  {
    title: 'Enter an organization number',
    copy: 'Nine digits is all the workspace needs to begin a lookup against the register.',
  },
  {
    title: 'Verify against Brreg',
    copy: 'Legal identity, address, and incorporation details are matched to the official record.',
  },
  {
    title: 'Collect and hash evidence',
    copy: 'The registry agent gathers supporting sources, stores them, and locks the delta hash.',
  },
  {
    title: 'Audit the lineage',
    copy: 'Open any record to see the full path from registry response to evidence row to claim.',
  },
]

export function HowItWorks() {
  return (
    <section id="how-it-works" className="border-b border-line bg-paper">
      <div className="page-shell py-20 lg:py-28">
        <Reveal className="max-w-2xl">
          <p className="kicker">How it works</p>
          <h2 className="mt-5 text-[clamp(1.9rem,3.6vw,2.75rem)] leading-[1.08] font-semibold tracking-[-0.035em] text-ink">
            From registry number to audited record.
          </h2>
        </Reveal>

        <ol className="mt-12 grid gap-px overflow-hidden rounded-card border border-line bg-line sm:grid-cols-2 xl:grid-cols-4">
          {steps.map((step, index) => (
            <li key={step.title} className="bg-paper">
              <Reveal delay={index * 70} className="flex h-full flex-col p-6 lg:p-7">
                <span className="mono-data text-[12px] font-medium text-accent">
                  {String(index + 1).padStart(2, '0')}
                </span>
                <h3 className="mt-4 text-[16px] font-semibold tracking-[-0.02em] text-ink">
                  {step.title}
                </h3>
                <p className="mt-2 text-[14px] leading-[1.6] text-graphite">{step.copy}</p>
              </Reveal>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}