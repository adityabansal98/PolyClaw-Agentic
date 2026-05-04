// Demo mode hook — reads ?demo=hw6|hw7|hw8 from URL params.
// When active, pages render mock data instead of fetching from API.
//
// Default behavior: when no `?demo=` param is present, the platform shows the
// HW8 30-agent stress-test view as the showcase landing experience. To see
// the empty live API instead, use `?demo=none` (or `?demo=live`).

export type DemoVersion = 'hw6' | 'hw7' | 'hw8' | null

const DEFAULT_DEMO: DemoVersion = 'hw8'

export function getDemoVersion(): DemoVersion {
  const params = new URLSearchParams(window.location.search)
  const v = params.get('demo')
  if (v === 'hw6' || v === 'hw7' || v === 'hw8') return v
  if (v === 'none' || v === 'live') return null
  return DEFAULT_DEMO
}

export function isDemoMode(): boolean {
  return getDemoVersion() !== null
}
