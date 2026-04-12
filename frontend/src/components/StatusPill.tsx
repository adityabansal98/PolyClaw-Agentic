import type { ReactNode } from 'react'

interface StatusPillProps {
  tone: 'neutral' | 'positive' | 'warning' | 'critical' | 'info'
  children: ReactNode
}

export function StatusPill({ tone, children }: StatusPillProps) {
  return <span className={`status-pill status-pill--${tone}`}>{children}</span>
}
