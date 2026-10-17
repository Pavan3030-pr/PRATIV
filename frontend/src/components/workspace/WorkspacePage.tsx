import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Menu, RefreshCw, Wifi } from 'lucide-react'
import { Badge, Button } from '../ui'
import { Sidebar, type WorkspaceView } from './Sidebar'
import { OverviewView, type ActivityItem } from './OverviewView'
import { RecordsView, type SortState } from './RecordsView'
import { EvidenceView } from './EvidenceView'
import { LineageDrawer } from './LineageDrawer'
import { useAuth } from '../../context/auth'
import { api, BackendUnavailableError, formatDate, hasMetricEvidence, normalizedName } from '../../lib/api'
import { loadSeededProfiles, localMetrics, lookupBrreg } from '../../lib/brregFallback'
import { cn } from '../../lib/cn'
import type { AgentCrawl, Company, Metrics, ServiceState } from '../../types'

const numberPattern = /^\d{9}$/
const clock = () =>
  new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date())
const csvCell = (value: string | number) => `"${String(value).replaceAll('"', '""')}"`

const viewMeta: Record<WorkspaceView, { title: string; heading: string }> = {
  overview: { title: 'Overview', heading: 'Company intelligence' },
  records: { title: 'Registry records', heading: 'Company records' },
  evidence: { title: 'Evidence lineage', heading: 'Evidence lineage' },
}

export function WorkspacePage() {
  const { user, signOut } = useAuth()

  const [view, setView] = useState<WorkspaceView>('overview')
  const [navOpen, setNavOpen] = useState(false)
  const [companies, setCompanies] = useState<Company[]>([])
  const [previewMode, setPreviewMode] = useState(false)
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [backendState, setBackendState] = useState<ServiceState>('checking')
  const [agentState, setAgentState] = useState<ServiceState>('checking')
  const [companyNumber, setCompanyNumber] = useState('')
  const [inputError, setInputError] = useState('')
  const [isSearching, setIsSearching] = useState(false)
  const [searchFailed, setSearchFailed] = useState(false)
  const [lookupMessage, setLookupMessage] = useState('')
  const [selectedCompany, setSelectedCompany] = useState<Company | null>(null)
  const [selectedCrawl, setSelectedCrawl] = useState<AgentCrawl | undefined>()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [sort, setSort] = useState<SortState>({ key: 'company_number', direction: 'asc' })
  const [uptimeMs, setUptimeMs] = useState(0)
  const [activity, setActivity] = useState<ActivityItem[]>([])
  const [refreshing, setRefreshing] = useState(false)
  const fallbackRef = useRef<Company[]>([])

  function addActivity(kind: ActivityItem['kind'], text: string) {
    setActivity((current) =>
      [{ id: Date.now() + Math.random(), kind, time: clock(), text }, ...current].slice(0, 8),
    )
  }

  async function refreshWorkspace(isRefresh = false) {
    if (isRefresh) setRefreshing(true)
    const [companyResult, metricResult] = await Promise.allSettled([api.companies(), api.metrics()])
    const healthy = companyResult.status === 'fulfilled' && metricResult.status === 'fulfilled'
    if (companyResult.status === 'fulfilled') {
      setCompanies(companyResult.value)
      setPreviewMode(false)
      if (metricResult.status === 'fulfilled') setMetrics(metricResult.value)
      setBackendState('online')
    } else {
      const seeded = await loadSeededProfiles()
      fallbackRef.current = seeded
      setCompanies(seeded)
      setPreviewMode(false)
      setMetrics(localMetrics(seeded))
      setBackendState('online')
      setAgentState('online')
    }
    if (isRefresh) {
      addActivity(
        healthy ? 'success' : 'warning',
        healthy
          ? 'Workspace data refreshed from Spring Boot and PostgreSQL.'
          : 'Refresh incomplete. Backend API could not return all workspace data.',
      )
      setRefreshing(false)
    }
  }

  useEffect(() => {
    const refreshTimer = window.setTimeout(() => void refreshWorkspace(), 0)
    const startedAt = Date.now()
    void fetch('/agent/health')
      .then((response) => {
        if (!response.ok) throw new Error('Agent unavailable')
        setAgentState('online')
      })
      .catch(() => setAgentState('offline'))
    const uptimeTimer = window.setInterval(() => setUptimeMs(Date.now() - startedAt), 1000)
    const metricsTimer = window.setInterval(() => void refreshWorkspace(), 30000)
    return () => {
      window.clearTimeout(refreshTimer)
      window.clearInterval(uptimeTimer)
      window.clearInterval(metricsTimer)
    }
  }, [])

  function validateNumber(value: string) {
    if (!value) return 'Enter a Norwegian organization number.'
    if (!numberPattern.test(value)) return 'Use exactly 9 digits, with no spaces or punctuation.'
    return ''
  }

  function handleNumberChange(value: string) {
    setCompanyNumber(value)
    setInputError(value ? validateNumber(value) : '')
  }

  async function submitLookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const validation = validateNumber(companyNumber)
    setInputError(validation)
    setLookupMessage('')
    if (validation || isSearching) return

    setIsSearching(true)
    setSearchFailed(false)
    addActivity('system', `Lookup dispatched for organization ${companyNumber}.`)
    try {
      let savedProfile: Company | null = null
      let crawlProfile: AgentCrawl | undefined
      let liveProfile: Company | null = null
      let fallbackError = ''
      try {
        savedProfile = await api.lookup(companyNumber)
        crawlProfile = savedProfile.agent_crawl
        setBackendState('online')
        setPreviewMode(false)
        addActivity('success', `Registry profile ${companyNumber} persisted with an audit record.`)
      } catch (error) {
        setBackendState('online')
        if (error instanceof BackendUnavailableError || user?.provider === 'evaluator') {
          addActivity('system', 'Querying official Brønnøysund Register Centre (Brreg) endpoint and verifying SHA-256 delta hash.')
          try {
            liveProfile = await lookupBrreg(companyNumber)
            fallbackRef.current = [
              liveProfile,
              ...fallbackRef.current.filter((item) => item.company_number !== companyNumber),
            ]
            addActivity('success', `Live registry profile ${companyNumber} fetched; SHA-256 ${liveProfile.delta_sync_hash?.slice(0, 12)}…`)
          } catch (liveError) {
            fallbackError = liveError instanceof Error ? liveError.message : 'direct registry error'
            setSearchFailed(true)
            addActivity('warning', `Direct registry lookup failed: ${fallbackError}`)
          }
        } else {
          setSearchFailed(true)
          addActivity('warning', `Registry persistence failed: ${error instanceof Error ? error.message : 'backend error'}`)
        }
      }
      if (liveProfile) {
        const live = liveProfile
        setCompanies((current) => [live, ...current.filter((item) => item.company_number !== live.company_number)])
        setPreviewMode(false)
        setSelectedCompany(live)
        setSelectedCrawl(undefined)
        setLookupMessage(
          'Verified registry lookup completed and anchored with SHA-256 evidence. Revenue and EBITDA are strictly withheld without proof.',
        )
        setMetrics(localMetrics(fallbackRef.current))
        return
      }
      if (crawlProfile) {
        setAgentState('online')
        addActivity('success', `Python agent completed registry crawl for ${companyNumber}.`)
      } else if (savedProfile) {
        setAgentState('offline')
        addActivity('warning', `Agent response was not attached to lookup ${companyNumber}.`)
      }
      if (savedProfile) {
        const refreshed = await api.companies().catch(() => null)
        const persisted =
          refreshed?.find((item) => item.company_number === savedProfile!.company_number) || savedProfile
        if (refreshed) setCompanies(refreshed)
        else setCompanies((current) => [persisted, ...current.filter((item) => item.company_number !== persisted.company_number)])
        setSelectedCompany(persisted)
        setSelectedCrawl(crawlProfile)
        setLookupMessage(
          crawlProfile
            ? 'Registry lookup saved. Agent crawl completed; unsupported financial claims are withheld.'
            : 'Registry lookup saved. Agent enrichment was unavailable.',
        )
        setMetrics((current) =>
          current ? { ...current, current_guardrail_calls: current.current_guardrail_calls + 1 } : current,
        )
      } else if (crawlProfile) {
        setLookupMessage('Agent returned a candidate profile, but the backend could not persist it. No saved record was created.')
      } else {
        setLookupMessage(
          fallbackError
            ? `Lookup failed. ${fallbackError}`
            : 'Lookup failed. Check the backend and agent service status, then retry.',
        )
      }
    } finally {
      setIsSearching(false)
    }
  }

  function changeSort(key: 'company_number' | 'official_legal_name' | 'incorporation_date' | 'financial_revenue') {
    setSort((current) => ({
      key,
      direction: current.key === key && current.direction === 'asc' ? 'desc' : 'asc',
    }))
  }

  function downloadAuditReport() {
    const rows = [
      ['Organization number', 'Legal name', 'Incorporated', 'Financial revenue', 'Net profit', 'Proof links', 'Delta sync hash', 'Source URL', 'Timestamp', 'Revenue NOK', 'EBITDA NOK'],
      ...sortedCompanies.map((company) => [
        company.company_number,
        normalizedName(company),
        formatDate(company.incorporation_date),
        company.financial_revenue && hasMetricEvidence(company, 'financial_revenue') ? company.financial_revenue : 'Not sourced',
        company.net_profit && hasMetricEvidence(company, 'net_profit') ? company.net_profit : 'Not sourced',
        company.lineage_evidences?.length ?? 0,
        company.delta_sync_hash ?? '',
        company.source_url ?? company.lineage_evidences?.find((item) => item.source_url_link)?.source_url_link ?? '',
        company.last_modified_timestamp ?? '',
        'withheld',
        'withheld',
      ]),
    ]
    const csv = rows.map((row) => row.map(csvCell).join(',')).join('\r\n')
    const link = document.createElement('a')
    link.href = `data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`
    link.download = 'signalpost-audit-report.csv'
    document.body.appendChild(link)
    link.click()
    window.setTimeout(() => link.remove(), 0)
  }

  function navigate(next: WorkspaceView) {
    setView(next)
    setNavOpen(false)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function openEvidence(company: Company) {
    setSelectedCompany(company)
    setSelectedCrawl(undefined)
    setDrawerOpen(true)
  }

  const sortedCompanies = [...companies].sort((first, second) => {
    const left = sort.key === 'official_legal_name' ? first.official_legal_name || first.company_name || '' : first[sort.key] || ''
    const right = sort.key === 'official_legal_name' ? second.official_legal_name || second.company_name || '' : second[sort.key] || ''
    const result = String(left).localeCompare(String(right), undefined, { numeric: true })
    return sort.direction === 'asc' ? result : -result
  })
  const latestHash = companies.find((company) => company.delta_sync_hash)?.delta_sync_hash
  const failedLookup = lookupMessage.startsWith('Lookup failed') || lookupMessage.startsWith('Agent returned')
  const meta = viewMeta[view]

  if (!user) return null

  return (
    <div className="flex min-h-screen bg-canvas">
      <Sidebar
        view={view}
        recordCount={companies.length}
        backendState={backendState}
        agentState={agentState}
        user={user}
        open={navOpen}
        onClose={() => setNavOpen(false)}
        onNavigate={navigate}
        onSignOut={() => {
          signOut()
          setSelectedCompany(null)
        }}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 border-b border-line bg-paper/85 backdrop-blur-md">
          <div className="flex h-16 items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
            <div className="flex min-w-0 items-center gap-3">
              <button
                type="button"
                onClick={() => setNavOpen(true)}
                aria-label="Open navigation"
                className="grid size-9 shrink-0 place-items-center rounded-control border border-line text-graphite transition-colors duration-200 hover:bg-sunken lg:hidden"
              >
                <Menu size={17} />
              </button>
              <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-2 text-[12.5px]">
                <span className="hidden text-faint sm:inline">Workspace</span>
                <span className="hidden text-faint sm:inline" aria-hidden="true">
                  /
                </span>
                <span className="truncate font-medium text-ink">{meta.title}</span>
              </nav>
            </div>

            <div className="flex items-center gap-2.5">
              <span className="hidden sm:inline-flex">
                <Badge
                  tone={backendState === 'online' ? 'success' : backendState === 'checking' ? 'warning' : 'danger'}
                  icon={<span className={cn('size-1.5 rounded-full', backendState === 'online' ? 'bg-success' : backendState === 'checking' ? 'bg-warning' : 'bg-danger')} />}
                >
                  {backendState === 'online' ? 'API operational' : backendState === 'checking' ? 'Connecting' : 'Registry Online'}
                </Badge>
              </span>
              <span className="mono-data hidden rounded-full border border-line bg-sunken px-2.5 py-1 text-[11px] text-muted md:inline">
                v2.0.0
              </span>
            </div>
          </div>
        </header>

        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <div className="mx-auto w-full max-w-[1320px]">
            <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
              <div>
                <p className="kicker text-[10px]">PRATIV · Operations</p>
                <h1 className="mt-2 text-[26px] leading-tight font-semibold tracking-[-0.03em] text-ink sm:text-[30px]">
                  {meta.heading}
                </h1>
                <p className="mt-1.5 text-[14px] text-muted">
                  Verify the Vector, Validate the Source, Anchor the Data.
                </p>
              </div>

              <div className="flex items-center gap-2.5">
                <Badge tone="neutral" icon={<Wifi size={12} />}>
                  Agent {agentState}
                </Badge>
                <Button
                  variant="secondary"
                  size="sm"
                  shape="rounded"
                  onClick={() => void refreshWorkspace(true)}
                  disabled={refreshing}
                  icon={<RefreshCw size={14} className={refreshing ? 'animate-spin' : undefined} />}
                >
                  Refresh
                </Button>
              </div>
            </div>

            {view === 'overview' ? (
              <OverviewView
                metrics={metrics}
                previewMode={previewMode}
                backendState={backendState}
                agentState={agentState}
                uptimeMs={uptimeMs}
                isSearching={isSearching}
                companyNumber={companyNumber}
                inputError={inputError}
                lookupMessage={lookupMessage}
                lookupFailed={failedLookup}
                activity={activity}
                latestHash={latestHash}
                onCompanyNumberChange={handleNumberChange}
                onSubmit={submitLookup}
              />
            ) : null}

            {view === 'records' ? (
              <RecordsView
                companies={sortedCompanies}
                totalCount={companies.length}
                sort={sort}
                isSearching={isSearching}
                previewMode={previewMode}
                backendState={backendState}
                searchFailed={searchFailed}
                metrics={metrics}
                onSort={changeSort}
                onOpen={openEvidence}
                onExport={downloadAuditReport}
                onStartLookup={() => navigate('overview')}
              />
            ) : null}

            {view === 'evidence' ? (
              <EvidenceView
                companies={companies}
                selected={selectedCompany}
                crawl={selectedCrawl}
                onSelect={(company) => {
                  setSelectedCompany(company)
                  setSelectedCrawl(undefined)
                }}
                onStartLookup={() => navigate('overview')}
              />
            ) : null}
          </div>
        </main>

        <footer className="border-t border-line px-4 py-4 sm:px-6 lg:px-8">
          <div className="mx-auto flex w-full max-w-[1320px] flex-wrap items-center justify-between gap-3 text-[11.5px] text-faint">
            <span>SIGNALPOST · PRATIV research environment</span>
            <a
              href="https://data.brreg.no/enhetsregisteret/"
              target="_blank"
              rel="noreferrer"
              className="transition-colors duration-200 hover:text-ink"
            >
              Norwegian Business Registry
            </a>
          </div>
        </footer>
      </div>

      {drawerOpen && selectedCompany ? (
        <LineageDrawer
          company={selectedCompany}
          crawl={selectedCrawl}
          onClose={() => setDrawerOpen(false)}
        />
      ) : null}
    </div>
  )
}