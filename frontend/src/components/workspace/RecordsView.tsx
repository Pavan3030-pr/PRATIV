import { ArrowDown, ArrowRight, ArrowUp, ChevronRight, CircleAlert, Download, FileSearch, LoaderCircle } from 'lucide-react'
import { Badge, Button } from '../ui'
import { cn } from '../../lib/cn'
import { formatDate, hasMetricEvidence, normalizedName } from '../../lib/api'
import type { Company, Metrics, ServiceState } from '../../types'

export type SortKey = 'company_number' | 'official_legal_name' | 'incorporation_date' | 'financial_revenue'
export type SortState = { key: SortKey; direction: 'asc' | 'desc' }

type RecordsViewProps = {
  companies: Company[]
  totalCount: number
  sort: SortState
  isSearching: boolean
  previewMode: boolean
  backendState: ServiceState
  searchFailed: boolean
  metrics: Metrics | null
  onSort: (key: SortKey) => void
  onOpen: (company: Company) => void
  onExport: () => void
  onStartLookup: () => void
}

function SortButton({
  label,
  sortKey,
  sort,
  onClick,
}: {
  label: string
  sortKey: SortKey
  sort: SortState
  onClick: (key: SortKey) => void
}) {
  const active = sort.key === sortKey
  return (
    <button
      type="button"
      onClick={() => onClick(sortKey)}
      className={cn(
        'inline-flex items-center gap-1.5 rounded transition-colors duration-200 hover:text-ink',
        active ? 'text-accent' : 'text-muted',
      )}
      aria-label={`Sort by ${label}`}
    >
      {label}
      {active ? (
        sort.direction === 'asc' ? (
          <ArrowUp size={12} aria-hidden="true" />
        ) : (
          <ArrowDown size={12} aria-hidden="true" />
        )
      ) : (
        <span className="text-faint/70" aria-hidden="true">
          ↕
        </span>
      )}
    </button>
  )
}

function FinancialCell({ value, sourced }: { value?: string; sourced: boolean }) {
  if (!value || !sourced) {
    return (
      <span className="inline-flex items-center gap-1.5 text-[12.5px] text-faint">
        <span className="size-1.5 rounded-full border border-line-strong" aria-hidden="true" />
        Not sourced
      </span>
    )
  }
  return <span className="mono-data text-[12.5px] text-ink">{value}</span>
}

export function RecordsView({
  companies,
  totalCount,
  sort,
  isSearching,
  previewMode,
  backendState,
  searchFailed,
  metrics,
  onSort,
  onOpen,
  onExport,
  onStartLookup,
}: RecordsViewProps) {
  const showTable =
    isSearching || ((backendState !== 'offline' || previewMode) && companies.length > 0)

  return (
    <div className="overflow-hidden rounded-card border border-line bg-paper">
      <div className="flex flex-wrap items-end justify-between gap-4 p-5 sm:p-6">
        <div>
          <p className="kicker text-[10px]">Cross-reference grid</p>
          <h2 className="mt-2 flex items-center gap-2.5 text-[18px] font-semibold tracking-[-0.03em] text-ink">
            Company records
            <span className="mono-data rounded-full border border-line bg-sunken px-2 py-0.5 text-[11px] font-medium text-muted">
              {totalCount}
            </span>
          </h2>
          <p className="mt-1.5 text-[13px] text-muted">
            Financial values appear only when matching metric-level evidence is stored.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden text-[11.5px] text-faint md:inline">Select a column to sort</span>
          <Button
            variant="secondary"
            size="sm"
            shape="rounded"
            onClick={onExport}
            disabled={companies.length === 0 || isSearching}
            icon={<Download size={14} />}
          >
            Export CSV
          </Button>
        </div>
      </div>

      {previewMode ? (
        <p className="flex items-start gap-2 border-t border-line bg-warning-soft px-5 py-3 text-[12.5px] leading-[1.55] text-warning sm:px-6">
          <CircleAlert size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
          Local preview only — the registry API is offline. Identities are illustrative; no source
          evidence or financial values are asserted.
        </p>
      ) : null}

      {searchFailed && !isSearching ? (
        <p
          role="alert"
          className="flex items-start gap-2 border-t border-line bg-warning-soft px-5 py-3 text-[12.5px] leading-[1.55] text-warning sm:px-6"
        >
          <CircleAlert size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
          Registry persistence failed — the request was isolated and no partial record was written.
        </p>
      ) : null}

      {showTable ? (
        <div className="scroll-area overflow-x-auto">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="border-y border-line bg-canvas">
                <th className="px-5 py-2.5 text-[11px] font-medium sm:px-6">
                  <SortButton label="Organization" sortKey="company_number" sort={sort} onClick={onSort} />
                </th>
                <th className="px-3 py-2.5 text-[11px] font-medium">
                  <SortButton label="Legal name" sortKey="official_legal_name" sort={sort} onClick={onSort} />
                </th>
                <th className="px-3 py-2.5 text-[11px] font-medium">
                  <SortButton label="Incorporated" sortKey="incorporation_date" sort={sort} onClick={onSort} />
                </th>
                <th className="px-3 py-2.5 text-[11px] font-medium">Revenue</th>
                <th className="px-3 py-2.5 text-[11px] font-medium">Net profit</th>
                <th className="px-3 py-2.5 text-[11px] font-medium">Proof</th>
                <th className="px-5 py-2.5 sm:pr-6">
                  <span className="sr-only">Open evidence</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {isSearching
                ? Array.from({ length: 3 }, (_, index) => (
                    <tr key={`skeleton-${index}`} aria-hidden="true">
                      <td colSpan={7} className="px-5 py-4 sm:px-6">
                        <span className="flex items-center gap-3 text-[13px] text-faint">
                          <LoaderCircle size={14} className="animate-spin" />
                          Querying registry…
                        </span>
                      </td>
                    </tr>
                  ))
                : companies.map((company) => {
                    const revenueSourced = hasMetricEvidence(company, 'financial_revenue')
                    const profitSourced = hasMetricEvidence(company, 'net_profit')
                    const rows = company.lineage_evidences?.length ?? 0
                    return (
                      <tr
                        key={company.company_number}
                        tabIndex={0}
                        onClick={() => onOpen(company)}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault()
                            onOpen(company)
                          }
                        }}
                        aria-label={`Open evidence for ${normalizedName(company)}`}
                        className={cn(
                          'cursor-pointer border-b border-line transition-colors duration-150 last:border-0 hover:bg-canvas',
                          previewMode && 'bg-warning-soft/40',
                        )}
                      >
                        <td className="px-5 py-3.5 sm:px-6">
                          <span className="mono-data text-[13px] text-ink">{company.company_number}</span>
                        </td>
                        <td className="max-w-[260px] px-3 py-3.5">
                          <span className="flex items-center gap-2">
                            <span className="truncate text-[13.5px] font-medium text-ink">
                              {normalizedName(company)}
                            </span>
                            {previewMode ? (
                              <Badge tone="warning" className="text-[10px]">
                                PREVIEW
                              </Badge>
                            ) : null}
                          </span>
                          <span className="mt-0.5 block truncate text-[12px] text-faint">
                            {company.registered_address || 'Address not recorded'}
                          </span>
                        </td>
                        <td className="px-3 py-3.5">
                          <span className="mono-data whitespace-nowrap text-[12.5px] text-graphite">
                            {formatDate(company.incorporation_date)}
                          </span>
                        </td>
                        <td className="px-3 py-3.5">
                          <FinancialCell value={company.financial_revenue} sourced={revenueSourced} />
                        </td>
                        <td className="px-3 py-3.5">
                          <FinancialCell value={company.net_profit} sourced={profitSourced} />
                        </td>
                        <td className="px-3 py-3.5">
                          <Badge tone={rows > 0 ? 'success' : 'neutral'}>{rows} rows</Badge>
                        </td>
                        <td className="px-5 py-3.5 text-right sm:pr-6">
                          <ChevronRight
                            size={16}
                            className="ml-auto text-faint transition-transform duration-200 group-hover:translate-x-0.5"
                            aria-hidden="true"
                          />
                        </td>
                      </tr>
                    )
                  })}
            </tbody>
          </table>
        </div>
      ) : backendState === 'offline' && !previewMode ? (
        <div className="flex flex-col items-center gap-3 border-t border-line px-5 py-14 text-center sm:px-6">
          <CircleAlert size={20} className="text-warning" aria-hidden="true" />
          <p className="text-[14px] font-medium text-ink">Backend connection unavailable</p>
          <p className="max-w-sm text-[13px] leading-[1.6] text-muted">
            Start the Spring Boot API and database to load persisted company profiles.
          </p>
          <Button variant="secondary" size="sm" shape="rounded" onClick={onStartLookup} icon={<ArrowRight size={14} />}>
            Open lookup console
          </Button>
        </div>
      ) : companies.length === 0 ? (
        <div className="flex flex-col items-center gap-3 border-t border-line px-5 py-14 text-center sm:px-6">
          <FileSearch size={20} className="text-accent" aria-hidden="true" />
          <p className="text-[14px] font-medium text-ink">
            {backendState === 'checking' ? 'Loading registry records' : 'No company profiles yet'}
          </p>
          <p className="max-w-sm text-[13px] leading-[1.6] text-muted">
            {backendState === 'checking'
              ? 'Reading from the backend database…'
              : 'Run a company lookup to create the first persisted profile.'}
          </p>
          <Button variant="secondary" size="sm" shape="rounded" onClick={onStartLookup} icon={<ArrowRight size={14} />}>
            Open lookup console
          </Button>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line bg-canvas px-5 py-3 text-[11.5px] text-faint sm:px-6">
        <span className="flex items-center gap-2">
          <span className="size-1.5 rounded-full border border-line-strong" aria-hidden="true" />
          Values with no evidence are withheld, not estimated.
        </span>
        <span>
          {previewMode
            ? 'Illustrative preview · not persisted'
            : metrics
              ? 'Updated from backend metrics'
              : 'Awaiting backend connection'}
        </span>
      </div>
    </div>
  )
}