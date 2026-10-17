import { GitBranch, LayoutDashboard, LogOut, ScrollText, Table2, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Brand } from '../Brand'
import { cn } from '../../lib/cn'
import type { AuthenticatedUser } from '../../lib/api'
import type { ServiceState } from '../../types'

export type WorkspaceView = 'overview' | 'records' | 'evidence'

const navItems: { id: WorkspaceView; label: string; icon: LucideIcon; meta?: string }[] = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'records', label: 'Registry records', icon: Table2 },
  { id: 'evidence', label: 'Evidence lineage', icon: GitBranch },
]

function StatusLine({ label, state }: { label: string; state: ServiceState }) {
  const tone =
    state === 'online'
      ? 'bg-success'
      : state === 'checking'
        ? 'bg-warning'
        : 'bg-danger'
  const text =
    state === 'online' ? 'Operational' : state === 'checking' ? 'Connecting' : 'Unavailable'
  return (
    <span className="flex items-center justify-between gap-3 text-[12px]">
      <span className="text-muted">{label}</span>
      <span className="flex items-center gap-2 text-graphite">
        <span className={cn('size-1.5 rounded-full', tone)} aria-hidden="true" />
        {text}
      </span>
    </span>
  )
}

type SidebarProps = {
  view: WorkspaceView
  recordCount: number
  backendState: ServiceState
  agentState: ServiceState
  user: AuthenticatedUser
  open: boolean
  onClose: () => void
  onNavigate: (view: WorkspaceView) => void
  onSignOut: () => void
}

export function Sidebar({
  view,
  recordCount,
  backendState,
  agentState,
  user,
  open,
  onClose,
  onNavigate,
  onSignOut,
}: SidebarProps) {
  return (
    <>
      {open ? (
        <div
          className="fixed inset-0 z-40 bg-ink/30 lg:hidden"
          aria-hidden="true"
          onClick={onClose}
          style={{ animation: 'fade-in 0.18s ease-out both' }}
        />
      ) : null}

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex w-[272px] flex-col border-r border-line bg-paper transition-transform duration-300 lg:sticky lg:top-0 lg:h-screen lg:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="flex h-16 shrink-0 items-center justify-between border-b border-line px-5">
          <Brand compact />
          <button
            type="button"
            onClick={onClose}
            aria-label="Close navigation"
            className="grid size-8 place-items-center rounded-control text-muted transition-colors duration-200 hover:bg-sunken hover:text-ink lg:hidden"
          >
            <X size={16} />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-5" aria-label="Workspace">
          <p className="px-2 text-[10px] font-medium tracking-[0.16em] text-faint uppercase">
            Workspace
          </p>
          <ul className="mt-3 space-y-1">
            {navItems.map((item) => {
              const active = item.id === view
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => onNavigate(item.id)}
                    aria-current={active ? 'page' : undefined}
                    className={cn(
                      'flex w-full items-center gap-3 rounded-control px-3 py-2.5 text-left text-[13.5px] font-medium transition-colors duration-200',
                      active
                        ? 'bg-accent-soft text-accent'
                        : 'text-graphite hover:bg-sunken hover:text-ink',
                    )}
                  >
                    <item.icon size={16} aria-hidden="true" />
                    <span className="flex-1">{item.label}</span>
                    {item.id === 'records' && recordCount > 0 ? (
                      <span className="mono-data rounded-full bg-sunken px-2 py-0.5 text-[10px] text-muted">
                        {recordCount}
                      </span>
                    ) : null}
                  </button>
                </li>
              )
            })}
          </ul>

          <div className="mt-7 border-t border-line px-2 pt-5">
            <p className="text-[10px] font-medium tracking-[0.16em] text-faint uppercase">
              Services
            </p>
            <div className="mt-3 space-y-2.5">
              <StatusLine label="Registry API" state={backendState} />
              <StatusLine label="Python agent" state={agentState} />
            </div>
            <a
              href="https://data.brreg.no/enhetsregisteret/"
              target="_blank"
              rel="noreferrer"
              className="mt-4 inline-flex items-center gap-1.5 text-[12px] text-accent transition-opacity duration-200 hover:opacity-75"
            >
              <ScrollText size={13} aria-hidden="true" />
              Brreg source registry
            </a>
          </div>
        </nav>

        <div className="shrink-0 border-t border-line p-3">
          <div className="flex items-center gap-3 rounded-control px-2 py-2">
            <span className="mono-data grid size-8 shrink-0 place-items-center rounded-full bg-ink text-[12px] font-semibold text-white">
              {user.name.slice(0, 1).toUpperCase()}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13px] font-medium text-ink">{user.name}</span>
              <span className="block truncate text-[11.5px] text-faint">
                {user.email || `${user.provider} session`}
              </span>
            </span>
            <button
              type="button"
              onClick={onSignOut}
              aria-label="Sign out"
              title="Sign out"
              className="grid size-8 shrink-0 place-items-center rounded-control text-muted transition-colors duration-200 hover:bg-sunken hover:text-ink"
            >
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </aside>
    </>
  )
}