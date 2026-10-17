import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { LoaderCircle } from 'lucide-react'
import { cn } from '../../lib/cn'

type Variant = 'primary' | 'secondary' | 'ghost' | 'quiet'
type Size = 'sm' | 'md' | 'lg'
type Shape = 'pill' | 'rounded'

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant
  size?: Size
  shape?: Shape
  loading?: boolean
  icon?: ReactNode
}

const variantClasses: Record<Variant, string> = {
  primary:
    'bg-ink text-white shadow-[0_1px_2px_rgba(0,0,0,0.18)] hover:bg-ink-soft active:translate-y-px',
  secondary:
    'border border-line-strong bg-paper text-ink hover:bg-sunken hover:border-faint active:translate-y-px',
  ghost: 'text-graphite hover:text-ink hover:bg-sunken',
  quiet: 'text-muted hover:text-ink',
}

const sizeClasses: Record<Size, string> = {
  sm: 'h-9 px-4 text-[13px]',
  md: 'h-11 px-6 text-sm',
  lg: 'h-12 px-7 text-[15px]',
}

export function Button({
  variant = 'primary',
  size = 'md',
  shape = 'pill',
  loading = false,
  icon,
  className,
  children,
  disabled,
  type = 'button',
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={cn(
        'inline-flex select-none items-center justify-center gap-2 whitespace-nowrap font-medium tracking-[-0.01em] transition-[background-color,border-color,color,transform,box-shadow] duration-200',
        'disabled:pointer-events-none disabled:opacity-45',
        variantClasses[variant],
        sizeClasses[size],
        shape === 'pill' ? 'rounded-full' : 'rounded-control',
        className,
      )}
      {...rest}
    >
      {loading ? <LoaderCircle size={16} className="animate-spin" aria-hidden="true" /> : icon}
      {children}
    </button>
  )
}