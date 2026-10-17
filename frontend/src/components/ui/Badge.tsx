import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from '../../lib/cn'

type Tone = 'neutral' | 'accent' | 'success' | 'warning' | 'danger' | 'inverse'

const tones: Record<Tone, string> = {
  neutral: 'border-line bg-sunken text-graphite',
  accent: 'border-accent/15 bg-accent-soft text-accent',
  success: 'border-success/15 bg-success-soft text-success',
  warning: 'border-warning/20 bg-warning-soft text-warning',
  danger: 'border-danger/15 bg-danger-soft text-danger',
  inverse: 'border-white/12 bg-white/5 text-white/70',
}

type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  tone?: Tone
  icon?: ReactNode
}

export function Badge({ tone = 'neutral', icon, className, children, ...rest }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-[3px] text-[11px] font-medium leading-5 whitespace-nowrap',
        tones[tone],
        className,
      )}
      {...rest}
    >
      {icon}
      {children}
    </span>
  )
}