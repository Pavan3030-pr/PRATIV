import { ArrowRight } from 'lucide-react'
import { Button, Reveal } from '../ui'

export function FinalCta({ onStart }: { onStart: () => void }) {
  return (
    <section className="border-b border-line bg-canvas py-20 lg:py-28">
      <Reveal className="page-shell max-w-3xl text-center">
        <p className="kicker justify-center">Start researching</p>
        <h2 className="mt-5 text-[clamp(2rem,4vw,3rem)] leading-[1.08] font-semibold tracking-[-0.035em] text-ink">
          Start with one organization number.
        </h2>
        <p className="mx-auto mt-5 max-w-xl text-[16px] leading-[1.7] text-graphite">
          Sign in with Google or GitHub and open the workspace. One lookup is enough to see a
          verified registry profile, its evidence rows, and the lineage behind every claim.
        </p>
        <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
          <Button size="lg" onClick={onStart} icon={<ArrowRight size={16} />}>
            Start researching
          </Button>
          <Button size="lg" variant="secondary" onClick={onStart}>
            Sign in to workspace
          </Button>
        </div>
        <p className="mt-6 text-[13px] text-faint">
          No credit card · Google & GitHub sign-in · Data sourced from Brreg
        </p>
      </Reveal>
    </section>
  )
}