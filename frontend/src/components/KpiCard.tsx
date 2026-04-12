import { formatPercent } from '../lib/format'
import { Sparkline } from './Sparkline'

interface KpiCardProps {
  label: string
  value: string
  helper: string
  delta?: string
  tone?: 'amber' | 'teal' | 'red' | 'blue'
  trend: number[]
  emphasis?: boolean
}

export function KpiCard({
  label,
  value,
  helper,
  delta,
  tone = 'amber',
  trend,
  emphasis = false,
}: KpiCardProps) {
  const first = trend[0] ?? 0
  const last = trend[trend.length - 1] ?? 0
  const trendDirection = last >= first ? 'up' : 'down'

  return (
    <article className={`kpi-card ${emphasis ? 'kpi-card--emphasis' : ''}`}>
      <div className="kpi-card__header">
        <p className="kpi-card__label">{label}</p>
        {delta ? (
          <span className={`delta-chip delta-chip--${trendDirection === 'up' ? 'positive' : 'critical'}`}>
            {delta}
          </span>
        ) : (
          <span className="delta-chip delta-chip--info">{formatPercent(last - first, 1)}</span>
        )}
      </div>
      <p className="kpi-card__value">{value}</p>
      <p className="muted">{helper}</p>
      <Sparkline values={trend} tone={tone} />
    </article>
  )
}
