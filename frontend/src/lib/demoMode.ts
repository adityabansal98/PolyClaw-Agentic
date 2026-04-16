// Demo mode hook — reads ?demo=hw6|hw7|hw8 from URL params.
// When active, pages render mock data instead of fetching from API.

export type DemoVersion = 'hw6' | 'hw7' | 'hw8' | null

export function getDemoVersion(): DemoVersion {
  const params = new URLSearchParams(window.location.search)
  const v = params.get('demo')
  if (v === 'hw6' || v === 'hw7' || v === 'hw8') return v
  return null
}

export function isDemoMode(): boolean {
  return getDemoVersion() !== null
}
