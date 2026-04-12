export function formatCurrency(value: number, digits = 0): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value)
}

export function formatSignedCurrency(value: number, digits = 0): string {
  const abs = formatCurrency(Math.abs(value), digits)
  if (value > 0) {
    return `+${abs}`
  }

  if (value < 0) {
    return `-${abs}`
  }

  return abs
}

export function formatPercent(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`
}

export function formatNumber(value: number, digits = 0): string {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value)
}

export function formatRelativeTime(value: string): string {
  const deltaMs = new Date(value).getTime() - Date.now()
  const formatter = new Intl.RelativeTimeFormat('en-US', { numeric: 'auto' })

  const units: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ['day', 1000 * 60 * 60 * 24],
    ['hour', 1000 * 60 * 60],
    ['minute', 1000 * 60],
    ['second', 1000],
  ]

  for (const [unit, size] of units) {
    if (Math.abs(deltaMs) >= size || unit === 'second') {
      return formatter.format(Math.round(deltaMs / size), unit)
    }
  }

  return 'just now'
}

export function formatCompactCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value)
}

export function titleCase(value: string): string {
  return value
    .split('-')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}
