import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'
import { normalizedName } from '../../lib/api'
import type { AgentCrawl, Company } from '../../types'
import { LineageDetail } from './LineageDetail'

type LineageDrawerProps = {
  company: Company
  crawl?: AgentCrawl
  onClose: () => void
}

export function LineageDrawer({ company, crawl, onClose }: LineageDrawerProps) {
  const closeButtonRef = useRef<HTMLButtonElement | null>(null)
  const returnFocusRef = useRef<Element | null>(null)

  useEffect(() => {
    returnFocusRef.current = document.activeElement
    closeButtonRef.current?.focus()
    return () => {
      if (returnFocusRef.current instanceof HTMLElement) returnFocusRef.current.focus()
    }
  }, [])

  const panelRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
      if (event.key !== 'Tab' || !panelRef.current) return
      // keep keyboard focus inside the modal dialog
      const focusable = panelRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), summary, input, select, textarea, [tabindex]:not([tabindex="-1"])',
      )
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
      style={{ animation: 'fade-in 0.18s ease-out both' }}
    >
      <div className="absolute inset-0 bg-ink/25" aria-hidden="true" />
      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="lineage-drawer-title"
        className="scroll-area relative flex h-full w-full max-w-[540px] flex-col overflow-y-auto bg-paper shadow-drawer"
        style={{ animation: 'drawer-in 0.32s cubic-bezier(0.22, 1, 0.36, 1) both' }}
      >
        <header className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-line bg-paper/95 px-5 py-4 backdrop-blur sm:px-6">
          <div>
            <p className="kicker text-[10px]">Audit record</p>
            <h2
              id="lineage-drawer-title"
              className="mt-1.5 text-[18px] font-semibold tracking-[-0.03em] text-ink"
            >
              Lineage &amp; proof
            </h2>
            <p className="mt-1 max-w-[340px] truncate text-[13px] text-muted">
              {normalizedName(company)} · {company.company_number}
            </p>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            aria-label="Close evidence drawer"
            className="grid size-9 shrink-0 place-items-center rounded-full border border-line bg-paper text-graphite transition-colors duration-200 hover:border-line-strong hover:bg-sunken hover:text-ink"
          >
            <X size={16} />
          </button>
        </header>

        <div className="px-5 py-6 sm:px-6">
          <LineageDetail company={company} crawl={crawl} />
        </div>
      </aside>
    </div>
  )
}