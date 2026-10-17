import { useState } from 'react'
import { ArrowLeft, ArrowRight, Check, Landmark, LockKeyhole, ShieldCheck, Waypoints } from 'lucide-react'
import { Brand } from '../Brand'
import { Button } from '../ui'
import { GoogleIcon, GithubIcon } from './ProviderIcons'
import { useAuth } from '../../context/auth'
import { oauthAuthorizationUrl } from '../../lib/api'

type OAuthProvider = 'google' | 'github'

const proofPoints = [
  {
    icon: ShieldCheck,
    title: 'Every fact has a trail',
    copy: 'Source URL, extraction snippet, and timestamp stored with the record.',
  },
  {
    icon: Landmark,
    title: 'Registry-first identity',
    copy: 'Legal identity anchored to the Norwegian Brønnøysund register.',
  },
  {
    icon: Waypoints,
    title: 'One lookup, clear provenance',
    copy: 'Agent discovery resolves into a durable, hashed audit record.',
  },
]

function ProviderButton({
  provider,
  busy,
  onStart,
}: {
  provider: OAuthProvider
  busy: boolean
  onStart: (provider: OAuthProvider) => void
}) {
  const isGoogle = provider === 'google'
  const label = isGoogle ? 'Continue with Google' : 'Continue with GitHub'
  return (
    <button
      type="button"
      onClick={() => onStart(provider)}
      disabled={busy}
      aria-busy={busy}
      className="group flex h-12 w-full items-center justify-between rounded-control border border-line-strong bg-paper px-4 text-[14px] font-medium text-ink transition-[border-color,background-color,transform] duration-200 hover:border-faint hover:bg-sunken active:translate-y-px disabled:pointer-events-none disabled:opacity-55"
    >
      <span className="flex items-center gap-3">
        {isGoogle ? <GoogleIcon /> : <GithubIcon />}
        {busy && isGoogle ? 'Opening Google…' : busy && !isGoogle ? 'Opening GitHub…' : label}
      </span>
      <ArrowRight
        size={15}
        className="text-faint transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-graphite"
        aria-hidden="true"
      />
    </button>
  )
}

export function AuthScreen({ onBack }: { onBack: () => void }) {
  const { error: sessionError, enterEvaluator } = useAuth()
  const [busyProvider, setBusyProvider] = useState<OAuthProvider | null>(null)
  const oauthRejected = new URLSearchParams(window.location.search).has('auth_error')
  const error = sessionError || (oauthRejected ? 'Sign-in could not be completed. Please try again.' : '')

  function beginSignIn(provider: OAuthProvider) {
    setBusyProvider(provider)
    window.location.assign(oauthAuthorizationUrl(provider))
  }

  return (
    <main className="flex min-h-screen flex-col bg-paper">
      <header className="border-b border-line">
        <div className="page-shell flex h-16 items-center justify-between">
          <Brand compact />
          <Button variant="ghost" size="sm" onClick={onBack} icon={<ArrowLeft size={15} />}>
            Back to overview
          </Button>
        </div>
      </header>

      <div className="page-shell grid flex-1 items-center gap-12 py-14 lg:grid-cols-[1.05fr_0.95fr] lg:gap-20 lg:py-20">
        <section
          aria-labelledby="auth-title"
          style={{ animation: 'rise-in 0.6s cubic-bezier(0.22, 1, 0.36, 1) both' }}
        >
          <p className="kicker text-accent">
            <span className="size-1.5 rounded-full bg-success" aria-hidden="true" />
            Company intelligence, with proof
          </p>

          <h1
            id="auth-title"
            className="mt-6 text-[clamp(2.25rem,4.4vw,3.5rem)] leading-[1.05] font-semibold tracking-[-0.04em] text-ink"
          >
            Know the company.
            <br />
            <span className="text-accent">Trust the source.</span>
          </h1>

          <p className="mt-5 max-w-md text-[15px] leading-[1.7] text-graphite">
            Verify the vector, validate the source, anchor the data. Your workspace keeps registry
            facts, evidence rows, and agent runs in one auditable place.
          </p>

          <div className="mt-9 h-px w-14 bg-line-strong" aria-hidden="true" />

          <ul className="mt-7 space-y-5">
            {proofPoints.map((point) => (
              <li key={point.title} className="flex gap-4">
                <span className="grid size-9 shrink-0 place-items-center rounded-panel border border-line bg-sunken">
                  <point.icon size={16} className="text-graphite" aria-hidden="true" />
                </span>
                <span>
                  <span className="block text-[14px] font-medium text-ink">{point.title}</span>
                  <span className="mt-0.5 block text-[13px] leading-[1.6] text-muted">
                    {point.copy}
                  </span>
                </span>
              </li>
            ))}
          </ul>

          <p className="mt-9 flex items-center gap-2 text-[13px] text-muted">
            <span className="grid size-5 place-items-center rounded-full bg-success-soft">
              <Check size={12} className="text-success" aria-hidden="true" />
            </span>
            Built for compliance, research, and diligence teams
          </p>
        </section>

        <section
          aria-label="Sign in to SIGNALPOST"
          className="rounded-card border border-line bg-canvas p-6 shadow-panel sm:p-8"
          style={{ animation: 'rise-in 0.6s cubic-bezier(0.22, 1, 0.36, 1) 0.1s both' }}
        >
          <p className="kicker">Workspace access</p>
          <h2 className="mt-3.5 text-[24px] leading-tight font-semibold tracking-[-0.03em] text-ink">
            Sign in to SIGNALPOST
          </h2>
          <p className="mt-2 text-[14px] leading-[1.6] text-muted">
            Continue with your work identity. Your provider password is never shared with
            SIGNALPOST.
          </p>

          <div className="mt-7 space-y-3">
            <ProviderButton provider="google" busy={busyProvider !== null} onStart={beginSignIn} />
            <ProviderButton provider="github" busy={busyProvider !== null} onStart={beginSignIn} />
            <button
              type="button"
              onClick={enterEvaluator}
              className="flex h-12 w-full items-center justify-center gap-2 rounded-control bg-ink px-4 text-[14px] font-medium text-paper transition-[opacity,transform] duration-200 hover:opacity-90 active:translate-y-px"
            >
              Enter Evaluator Workspace
              <ArrowRight size={15} aria-hidden="true" />
            </button>
          </div>
          <p className="mt-3 text-center text-[12px] leading-[1.5] text-faint">
            No account needed. If the backend is offline, lookups query the Brønnøysund register
            directly from your browser.
          </p>

          {error ? (
            <p
              role="alert"
              className="mt-5 flex items-start gap-2 rounded-control border border-danger/15 bg-danger-soft px-3.5 py-3 text-[13px] leading-[1.5] text-danger"
            >
              <span className="mono-data mt-px text-[11px] font-semibold" aria-hidden="true">
                !
              </span>
              {error}
            </p>
          ) : null}

          <div className="mt-6 flex items-start gap-3 rounded-control border border-line bg-paper p-3.5">
            <LockKeyhole size={15} className="mt-0.5 shrink-0 text-accent" aria-hidden="true" />
            <p className="text-[12px] leading-[1.6] text-muted">
              Sign-in is handled by Google or GitHub over OAuth 2.0. The workspace issues a
              short-lived bearer session for API calls.
            </p>
          </div>

          {busyProvider ? (
            <p className="mt-4 text-center text-[12px] text-faint" role="status">
              Completing secure handoff — you'll be returned here automatically.
            </p>
          ) : null}
        </section>
      </div>

      <footer className="border-t border-line">
        <div className="page-shell flex min-h-14 flex-col justify-center gap-2 py-4 text-[12px] text-faint sm:flex-row sm:items-center sm:justify-between">
          <span>© 2026 SIGNALPOST · PRATIV</span>
          <span className="hidden sm:inline">Company intelligence with a chain of custody</span>
          <a
            href="https://data.brreg.no/enhetsregisteret/"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 transition-colors duration-200 hover:text-ink"
          >
            Brønnøysund Register Centre
            <ArrowRight size={12} aria-hidden="true" />
          </a>
        </div>
      </footer>
    </main>
  )
}