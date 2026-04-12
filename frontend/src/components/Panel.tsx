import type { ReactNode } from 'react'

interface PanelProps {
  title: string
  subtitle?: string
  action?: ReactNode
  children: ReactNode
  className?: string
}

export function Panel({ title, subtitle, action, children, className }: PanelProps) {
  return (
    <section className={`panel ${className ?? ''}`.trim()}>
      <header className="panel__header">
        <div>
          <p className="eyebrow">{title}</p>
          {subtitle ? <p className="panel__subtitle">{subtitle}</p> : null}
        </div>
        {action ? <div className="panel__action">{action}</div> : null}
      </header>
      {children}
    </section>
  )
}
