import type { InputHTMLAttributes, ReactNode } from 'react'
import { cn } from '../../lib/cn'

export function Field({
  label,
  hint,
  htmlFor,
  children,
  className,
}: {
  label: ReactNode
  hint?: ReactNode
  htmlFor?: string
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn('space-y-2', className)}>
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={htmlFor} className="text-[13px] font-medium text-ink">
          {label}
        </label>
        {hint ? <span className="text-[11px] text-faint">{hint}</span> : null}
      </div>
      {children}
    </div>
  )
}

type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  invalid?: boolean
  leading?: ReactNode
  trailing?: ReactNode
}

export function Input({ invalid, leading, trailing, className, ...rest }: InputProps) {
  return (
    <div
      className={cn(
        'flex h-11 items-center gap-2.5 rounded-control border bg-paper px-3 transition-[border-color,box-shadow] duration-200',
        'focus-within:border-accent focus-within:shadow-[0_0_0_3px_rgba(67,56,202,0.12)]',
        invalid
          ? 'border-danger/60 shadow-[0_0_0_3px_rgba(185,28,28,0.10)]'
          : 'border-line-strong hover:border-faint',
        className,
      )}
    >
      {leading ? <span className="text-faint">{leading}</span> : null}
      <input
        className="h-full min-w-0 flex-1 border-0 bg-transparent text-sm text-ink outline-none"
        aria-invalid={invalid || undefined}
        {...rest}
      />
      {trailing ? <span className="shrink-0 text-[11px] text-faint">{trailing}</span> : null}
    </div>
  )
}