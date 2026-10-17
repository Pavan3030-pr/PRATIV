import { Brand } from '../Brand'
import { Button } from '../ui'

const links = [
  { label: 'Platform', href: '#platform' },
  { label: 'Verification', href: '#verification' },
  { label: 'How it works', href: '#how-it-works' },
  { label: 'Architecture', href: '#architecture' },
]

export function SiteHeader({ onStart }: { onStart: () => void }) {
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-paper/85 backdrop-blur-md">
      <div className="page-shell flex h-16 items-center justify-between gap-6">
        <a href="#top" aria-label="SIGNALPOST home" className="shrink-0 rounded-md">
          <Brand compact />
        </a>

        <nav aria-label="Primary" className="hidden items-center gap-7 lg:flex">
          {links.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="text-[13px] text-muted transition-colors duration-200 hover:text-ink"
            >
              {link.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <span className="hidden sm:block">
            <Button variant="ghost" size="sm" onClick={onStart}>
              Sign in
            </Button>
          </span>
          <Button size="sm" onClick={onStart}>
            Start researching
          </Button>
        </div>
      </div>
    </header>
  )
}