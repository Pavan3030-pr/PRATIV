import type { FormEvent, ReactNode } from 'react'
import { Activity, ArrowRight, CircleAlert, CircleHelp, Database, Fingerprint, LoaderCircle, Search, ShieldCheck, Waypoints } from 'lucide-react'
import { Badge, Button, Field, Input } from '../ui'
import { cn } from '../../lib/cn'
import type { Metrics, ServiceState } from '../../types'

export type ActivityItem = { id: number; time: string; kind: 'success' | 'warning' | 'system'; text: string }

type OverviewViewProps = {
  metrics: Metrics | null
  previewMode: boolean
  backendState: ServiceState
  agentState: ServiceState
  uptimeMs: number
  isSearching: boolean
  companyNumber: string
  inputError: string
  lookupMessage: string
  lookupFailed: boolean
  activity: ActivityItem[]
  latestHash?: string
  onCompanyNumberChange: (value: string) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
}

function StatCard({
  label,
  icon,
  value,
  caption,
  status,
  progress,
}: {
  label: string
  icon: ReactNode
  value: ReactNode
  caption: string
  status?: { text: string; tone: string }
  /** 0–100, rendered as a hairline usage bar. */
  progress?: number
}) {
  return (
    <div className="rounded-card border border-line bg-paper p-4 sm:p-5">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[12.5px] font-medium text-muted">{label}</span>
        <span className="text-faint">{icon}</span>
      </div>
      <p className="mono-data mt-3 truncate text-[26px] leading-none font-semibold tracking-[-0.03em] text-ink">
        {value}
      </p>
      {typeof progress === 'number' ? (
        <div className="mt-3.5 h-1 overflow-hidden rounded-full bg-sunken" role="presentation">
          <span
            className="block h-full rounded-full bg-accent transition-[width] duration-500"
            style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
          />
        </div>
      ) : null}
      <div className="mt-4 flex items-center justify-between gap-3 border-t border-line pt-3 text-[11px] text-faint">
        {status ? (
          <span className="flex items-center gap-1.5 font-medium">
            <span className={cn('size-1.5 rounded-full', status.tone)} aria-hidden="true" />
            {status.text}
          </span>
        ) : null}
        <span className="truncate">{caption}</span>
      </div>
    </div>
  )
}

function TelemetryRow({ label, value, hint }: { label: string; value: ReactNode; hint: string }) {
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3 sm:px-5">
      <span className="text-[12.5px] text-muted">{label}</span>
      <span className="flex items-baseline gap-2">
        <span className="mono-data text-[13px] font-medium text-ink">{value}</span>
        <span className="hidden text-[11px] text-faint sm:inline">{hint}</span>
      </span>
    </div>
  )
}

export function OverviewView({
  metrics,
  previewMode,
  backendState,
  agentState,
  uptimeMs,
  isSearching,
  companyNumber,
  inputError,
  lookupMessage,
  lookupFailed,
  activity,
  latestHash,
  onCompanyNumberChange,
  onSubmit,
}: OverviewViewProps) {
  const remaining = metrics ? Math.max(0, metrics.max_guardrail_cap - metrics.current_guardrail_calls) : null
  const budgetPercent = metrics
    ? Math.min(100, (metrics.current_guardrail_calls / Math.max(metrics.max_guardrail_cap, 1)) * 100)
    : 0
  const uptimeLabel = `${String(Math.floor(uptimeMs / 3600000)).padStart(2, '0')}:${String(
    Math.floor((uptimeMs % 3600000) / 60000),
  ).padStart(2, '0')}:${String(Math.floor((uptimeMs % 60000) / 1000)).padStart(2, '0')}`

  return (
    <div className="space-y-4">
      <section aria-label="Workspace metrics" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Company profiles"
          icon={<Database size={16} />}
          value={metrics?.compiled_companies_count ?? (previewMode ? '05' : '—')}
          caption={previewMode ? 'Illustrative preview' : 'PostgreSQL records'}
          status={{
            text: previewMode ? 'PREVIEW' : backendState === 'online' ? 'LIVE' : 'CHECKING',
            tone: previewMode ? 'bg-warning' : backendState === 'online' ? 'bg-success' : 'bg-faint',
          }}
        />
        <StatCard
          label="Source evidence"
          icon={<ShieldCheck size={16} />}
          value={metrics?.lineage_evidences_count ?? '—'}
          caption="Linked proof rows"
          status={{
            text: backendState === 'online' ? 'SYNCED' : 'LOCAL',
            tone: backendState === 'online' ? 'bg-success' : 'bg-faint',
          }}
        />
        <StatCard
          label="Delta signature"
          icon={<Fingerprint size={16} />}
          value={latestHash ? `${latestHash.slice(0, 12)}…` : 'Awaiting sync'}
          caption="SHA-256 profile hash"
        />
        <StatCard
          label="Guardrail budget"
          icon={<Waypoints size={16} />}
          value={
            <>
              {remaining?.toLocaleString() ?? '—'}
              <span className="text-[15px] font-medium text-faint">
                {' '}
                / {metrics?.max_guardrail_cap?.toLocaleString() ?? '—'}
              </span>
            </>
          }
          caption={`${metrics?.current_guardrail_calls ?? '—'} used`}
          progress={budgetPercent}
        />
      </section>

      <section className="overflow-hidden rounded-card border border-line bg-paper">
        <div className="divide-y divide-line sm:grid sm:grid-cols-3 sm:divide-x sm:divide-y-0">
          <TelemetryRow label="Session uptime" value={uptimeLabel} hint="HH:MM:SS" />
          <TelemetryRow
            label="Agent threads"
            value={metrics ? (metrics.virtual_threads_active ? 'ACTIVE' : 'IDLE') : '—'}
            hint="Java 21 virtual"
          />
          <TelemetryRow
            label="Registry API"
            value={backendState === 'online' ? 'CONNECTED' : backendState === 'checking' ? 'CHECKING' : 'OFFLINE'}
            hint="Polls every 30s"
          />
        </div>
      </section>

      <section className="grid gap-3 xl:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
        <div className="rounded-card border border-line bg-paper p-5 sm:p-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="kicker text-[10px]">Registry lookup</p>
              <h2 className="mt-2 text-[18px] font-semibold tracking-[-0.03em] text-ink">
                Find a company
              </h2>
            </div>
            <span className="mono-data rounded-full border border-line bg-sunken px-2.5 py-1 text-[11px] text-muted">
              9 digits
            </span>
          </div>

          <p className="mt-2 max-w-md text-[13px] leading-[1.6] text-muted">
            Look up a Norwegian organization number across the official register and persist a
            linked audit record.
          </p>

          <form className="mt-5" onSubmit={onSubmit} noValidate>
            <Field
              htmlFor="company-number"
              label="Organization number"
              hint={
                <span className="group relative inline-flex items-center gap-1.5">
                  <span className="mono-data">9 digits</span>
                  <button
                    type="button"
                    aria-label="Organization number format requirements"
                    className="text-faint transition-colors duration-200 hover:text-graphite"
                  >
                    <CircleHelp size={13} />
                  </button>
                  <span
                    role="tooltip"
                    className="pointer-events-none absolute top-full right-0 z-20 mt-2 w-64 rounded-control border border-ink/10 bg-ink px-3 py-2.5 text-left text-[12px] leading-[1.55] text-white/80 opacity-0 shadow-lift transition-opacity duration-200 group-hover:opacity-100 group-focus-within:opacity-100"
                  >
                    <span className="mono-data block text-[11px] text-indigo-300">^\d&#123;9&#125;$</span>
                    Exactly nine digits, matching the Brreg organization number format.
                  </span>
                </span>
              }
            >
              <Input
                id="company-number"
                name="company-number"
                placeholder="e.g. 923609016"
                value={companyNumber}
                onChange={(event) => onCompanyNumberChange(event.target.value)}
                invalid={Boolean(inputError)}
                inputMode="numeric"
                autoComplete="off"
                maxLength={32}
                pattern="\d{9}"
                required
                leading={<Search size={16} />}
                trailing={`${companyNumber.length}/9`}
                aria-describedby={inputError ? 'company-number-error' : undefined}
                className="mono-data"
              />
            </Field>

            {inputError ? (
              <p id="company-number-error" role="alert" className="mt-2 flex items-center gap-1.5 text-[12px] text-danger">
                <CircleAlert size={13} aria-hidden="true" />
                {inputError}
              </p>
            ) : null}

            <Button
              type="submit"
              className="mt-4 w-full"
              size="md"
              disabled={isSearching || Boolean(inputError) || !companyNumber}
              loading={isSearching}
              icon={isSearching ? undefined : <ArrowRight size={15} />}
            >
              {isSearching ? 'Running registry + agent checks…' : 'Run verified lookup'}
            </Button>
          </form>

          {lookupMessage ? (
            <p
              role="status"
              className={cn(
                'mt-4 flex items-start gap-2 rounded-control border px-3.5 py-3 text-[12.5px] leading-[1.55]',
                lookupFailed
                  ? 'border-warning/20 bg-warning-soft text-warning'
                  : 'border-success/15 bg-success-soft text-success',
              )}
            >
              {lookupFailed ? (
                <CircleAlert size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
              ) : (
                <LoaderCircle size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
              )}
              {lookupMessage}
            </p>
          ) : null}

          <div className="mt-5 flex flex-wrap gap-x-5 gap-y-2 border-t border-line pt-4 text-[11.5px] text-muted">
            <span className="flex items-center gap-2">
              <span className="size-1.5 rounded-full bg-accent" aria-hidden="true" />
              Enhetsregisteret
            </span>
            <span className="flex items-center gap-2">
              <span className="size-1.5 rounded-full bg-warning" aria-hidden="true" />
              LangGraph agent
            </span>
            <span className="flex items-center gap-2">
              <span className="size-1.5 rounded-full bg-success" aria-hidden="true" />
              Evidence store
            </span>
          </div>
        </div>

        <div className="rounded-card border border-line bg-paper p-5 sm:p-6">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="kicker text-[10px]">Execution trace</p>
              <h2 className="mt-2 text-[18px] font-semibold tracking-[-0.03em] text-ink">
                Audited activity
              </h2>
            </div>
            <Badge tone="success" icon={<span className="size-1.5 rounded-full bg-success" />}>
              EVENT LOG
            </Badge>
          </div>

          <div className="mt-4 min-h-[196px] overflow-hidden rounded-control border border-line bg-canvas" aria-live="polite">
            {activity.length === 0 ? (
              <div className="flex h-[196px] flex-col items-center justify-center gap-2 text-center">
                <Activity size={18} className="text-faint" aria-hidden="true" />
                <p className="text-[13px] font-medium text-graphite">Waiting for workspace actions</p>
                <p className="max-w-xs text-[12px] text-faint">
                  Lookups, refreshes, and agent runs will appear here.
                </p>
              </div>
            ) : (
              <ul className="scroll-area max-h-[196px] divide-y divide-line overflow-y-auto">
                {activity.slice(0, 6).map((item) => (
                  <li key={item.id} className="grid grid-cols-[auto_1fr] items-start gap-3 px-4 py-3">
                    <time className="mono-data pt-0.5 text-[11px] text-faint">{item.time}</time>
                    <span className="flex gap-2.5">
                      <span
                        className={cn(
                          'mt-1.5 size-1.5 shrink-0 rounded-full',
                          item.kind === 'success'
                            ? 'bg-success'
                            : item.kind === 'warning'
                              ? 'bg-warning'
                              : 'bg-accent',
                        )}
                        aria-hidden="true"
                      />
                      <span className="text-[12.5px] leading-[1.55] text-graphite">{item.text}</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-4 text-[11.5px] text-faint">
            <span className="flex items-center gap-1.5">
              <Waypoints size={13} aria-hidden="true" />
              Agent: {agentState === 'online' ? 'responding' : agentState === 'checking' ? 'checking' : 'offline'}
            </span>
            <span>
              {backendState === 'online'
                ? 'Registry API connected'
                : backendState === 'checking'
                  ? 'Checking connection'
                  : 'API unavailable — preview data only'}
            </span>
          </div>
        </div>
      </section>
    </div>
  )
}