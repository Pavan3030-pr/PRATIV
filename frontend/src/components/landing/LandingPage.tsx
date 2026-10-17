import { Architecture } from './Architecture'
import { FeatureGrid } from './FeatureGrid'
import { FinalCta } from './FinalCta'
import { Hero } from './Hero'
import { HowItWorks } from './HowItWorks'
import { Narrative } from './Narrative'
import { SiteFooter } from './SiteFooter'
import { SiteHeader } from './SiteHeader'
import { TrustStrip } from './TrustStrip'

export function LandingPage({ onStart }: { onStart: () => void }) {
  return (
    <div className="bg-paper">
      <SiteHeader onStart={onStart} />
      <main>
        <Hero onStart={onStart} />
        <TrustStrip />
        <Narrative />
        <FeatureGrid />
        <HowItWorks />
        <Architecture />
        <FinalCta onStart={onStart} />
      </main>
      <SiteFooter />
    </div>
  )
}