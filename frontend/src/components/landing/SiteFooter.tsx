import { ArrowUpRight } from 'lucide-react'
import { Brand } from '../Brand'

const columns = [
  {
    title: 'Platform',
    items: ['Registry verification', 'Evidence hashing', 'Semantic lineage', 'Guard-railed agents'],
  },
  {
    title: 'Workspace',
    items: ['Company lookup', 'Evidence drawer', 'Audit export', 'Session telemetry'],
  },
  {
    title: 'Trust',
    items: ['Google & GitHub SSO', 'JWT bearer sessions', 'Withheld without proof', 'Audit-ready records'],
  },
]

export function SiteFooter() {
  return (
    <footer className="bg-ink text-white">
      <div className="page-shell py-14">
        <div className="grid gap-10 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
          <div>
            <Brand inverse />
            <p className="mt-4 max-w-xs text-[13px] leading-[1.65] text-white/50">
              Source-first company research. Official registry data, evidence lineage, and agentic
              verification for teams that cannot afford unverified facts.
            </p>
            <p className="mono-data mt-5 text-[11px] text-white/35">
              Verify the vector. Validate the source. Anchor the data.
            </p>
          </div>

          {columns.map((column) => (
            <nav key={column.title} aria-label={column.title}>
              <h3 className="text-[11px] font-medium tracking-[0.16em] text-white/40 uppercase">
                {column.title}
              </h3>
              <ul className="mt-4 space-y-2.5">
                {column.items.map((item) => (
                  <li key={item}>
                    <span className="text-[13px] text-white/65 transition-colors duration-200 hover:text-white">
                      {item}
                    </span>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>

        <div className="mt-12 flex flex-col gap-3 border-t border-white/10 pt-6 text-[12px] text-white/40 sm:flex-row sm:items-center sm:justify-between">
          <span>© 2026 SIGNALPOST · PRATIV. All rights reserved.</span>
          <a
            href="https://data.brreg.no/enhetsregisteret/"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 transition-colors duration-200 hover:text-white"
          >
            Norwegian Business Registry
            <ArrowUpRight size={13} aria-hidden="true" />
          </a>
        </div>
      </div>
    </footer>
  )
}