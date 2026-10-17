type BrandProps = {
  compact?: boolean
  /** Use on dark surfaces such as the footer. */
  inverse?: boolean
  /** Small line under the wordmark; hidden in compact mode. */
  tagline?: boolean
}

/**
 * SIGNALPOST wordmark. The glyph plots a trace that terminates on a
 * verified node — the product's lineage promise in miniature.
 */
export function Brand({ compact = false, inverse = false, tagline = false }: BrandProps) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <svg
        viewBox="0 0 40 40"
        aria-hidden="true"
        className={compact ? 'size-7 shrink-0' : 'size-9 shrink-0'}
      >
        <rect width="40" height="40" rx="11" fill={inverse ? '#ffffff' : '#0a0a0a'} />
        <path
          d="M10.5 26.5 17.5 19.5l4.6 4.4L28.5 14"
          fill="none"
          stroke={inverse ? '#0a0a0a' : '#ffffff'}
          strokeWidth="2.3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="10.5" cy="26.5" r="2.1" fill={inverse ? '#0a0a0a' : '#ffffff'} opacity="0.55" />
        <circle cx="28.5" cy="14" r="3.4" fill="#6366f1" />
      </svg>
      <span className="flex flex-col leading-none">
        <span
          className={`font-semibold tracking-[-0.03em] ${compact ? 'text-[15px]' : 'text-[17px]'} ${
            inverse ? 'text-white' : 'text-ink'
          }`}
        >
          SIGNALPOST
        </span>
        {tagline && !compact ? (
          <span className="mt-1.5 text-[10px] font-medium tracking-[0.14em] text-faint uppercase">
            Company intelligence · PRATIV
          </span>
        ) : null}
      </span>
    </span>
  )
}