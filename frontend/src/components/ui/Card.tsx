import type { HTMLAttributes } from 'react'
import { cn } from '../../lib/cn'

type CardProps = HTMLAttributes<HTMLDivElement> & {
  /** `flush` removes padding for tables and lists that own their spacing. */
  padded?: boolean
  interactive?: boolean
}

export function Card({ padded = true, interactive = false, className, children, ...rest }: CardProps) {
  return (
    <div
      className={cn(
        'border border-line bg-paper',
        padded && 'p-5 sm:p-6',
        interactive &&
          'transition-[border-color,box-shadow,transform] duration-200 hover:border-line-strong hover:shadow-lift',
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  )
}