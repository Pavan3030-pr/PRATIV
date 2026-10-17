import { ArrowRight, GitBranch } from 'lucide-react'
import { Badge, Button } from '../ui'
import type { AgentCrawl, Company } from '../../types'
import { normalizedName } from '../../lib/api'
import { LineageDetail } from './LineageDetail'

type EvidenceViewProps = {
  companies: Company[]
  selected?: Company | null
  crawl?: AgentCrawl
  onSelect: (company: Company) => void
  onStartLookup: () => void
}

export function EvidenceView({ companies, selected, crawl, onSelect, onStartLookup }: EvidenceViewProps) {
  if (!selected) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-card border border-line bg-paper px-5 py-16 text-center sm:px-6">
        <span className="grid size-11 place-items-center rounded-panel border border-line bg-sunken">
          <GitBranch size={19} className="text-accent" aria-hidden="true" />
        </span>
        <p className="text-[15px] font-medium text-ink">Select a record to audit</p>
        <p className="max-w-md text-[13.5px] leading-[1.6] text-muted">
          Evidence lineage shows the full path from registry response to evidence row to claim —
          including anything that is withheld for lack of proof.
        </p>
        <Button size="sm" shape="rounded" onClick={onStartLookup} icon={<ArrowRight size={14} />}>
          Run a registry lookup
        </Button>
      </div>
    )
  }

  return (
    <div className="rounded-card border border-line bg-paper">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-line p-5 sm:p-6">
        <div className="min-w-0">
          <p className="kicker text-[10px]">Evidence lineage</p>
          <p className="mt-2 max-w-md text-[13px] leading-[1.6] text-muted">
            Full path from registry response to evidence row to claim, including anything withheld
            for lack of proof.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Badge tone="success" icon={<span className="size-1.5 rounded-full bg-success" />}>
            Registry record
          </Badge>
          {companies.length > 0 ? (
            <label className="flex items-center gap-2 text-[12.5px] text-muted">
              <span className="sr-only">Choose a company record</span>
              <select
                value={selected.company_number}
                onChange={(event) => {
                  const next = companies.find((item) => item.company_number === event.target.value)
                  if (next) onSelect(next)
                }}
                className="h-9 max-w-[240px] rounded-control border border-line-strong bg-paper px-3 text-[13px] text-ink transition-colors duration-200 hover:border-faint focus:border-accent focus:outline-none"
              >
                {companies.map((company) => (
                  <option key={company.company_number} value={company.company_number}>
                    {normalizedName(company)} · {company.company_number}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
        </div>
      </div>

      <div className="p-5 sm:p-6">
        <LineageDetail company={selected} crawl={crawl} />
      </div>
    </div>
  )
}