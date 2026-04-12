interface SparklineProps {
  values: number[]
  tone?: 'amber' | 'teal' | 'red' | 'blue'
}

export function Sparkline({ values, tone = 'amber' }: SparklineProps) {
  if (values.length === 0) {
    return null
  }

  const width = 160
  const height = 46
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = Math.max(max - min, 0.001)

  const points = values
    .map((value, index) => {
      const x = (index / Math.max(values.length - 1, 1)) * width
      const y = height - ((value - min) / range) * height
      return `${x},${y}`
    })
    .join(' ')

  return (
    <svg className={`sparkline sparkline--${tone}`} viewBox={`0 0 ${width} ${height}`} role="presentation">
      <polyline points={points} fill="none" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
