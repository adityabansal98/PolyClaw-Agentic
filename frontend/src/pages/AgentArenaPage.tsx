// Phase 2b replacement for the old AgentArenaPage.
//
// The toy coin arena (legacy /api/arena/* endpoints) was deleted in Phase 2b —
// every old route returns 410 Gone. This page now renders the minimal
// /api/v1/leaderboard scaffold that reads from portfolio_snapshots. The full
// leaderboard with composite metrics (Sharpe, drawdown, Calmar) and season
// drilldowns arrives in Phase 4 along with the Season engine.
//
// Most of the old page's drilldowns (per-market bets, per-agent bets, ticker)
// depended on data the new store doesn't carry yet — they're intentionally
// removed here rather than hidden behind feature flags.

import { useEffect, useState } from 'react'

type LeaderboardRow = {
  agent_id: string
  name: string
  tier: string
  total_equity: number
  return_pct: number
  last_update_ms: number | null
}

type LeaderboardResponse = {
  items: LeaderboardRow[]
  legacy_note?: string
}

const EMPTY: LeaderboardResponse = { items: [] }

function formatPct(value: number): string {
  const pct = value * 100
  const sign = pct >= 0 ? '+' : ''
  return `${sign}${pct.toFixed(2)}%`
}

function formatUsdc(value: number): string {
  return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function formatTimestamp(ms: number | null): string {
  if (ms === null) return '—'
  return new Date(ms).toLocaleString()
}

export function AgentArenaPage() {
  const [data, setData] = useState<LeaderboardResponse>(EMPTY)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function refresh() {
    try {
      const response = await fetch('/api/v1/leaderboard')
      const payload = (await response.json()) as LeaderboardResponse | { error?: string }
      if (!response.ok) {
        const message = 'error' in payload && payload.error ? payload.error : `Request failed: ${response.status}`
        throw new Error(message)
      }
      setData(payload as LeaderboardResponse)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load leaderboard.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 30_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="arena-page">
      <header className="arena-header">
        <div>
          <h2>Leaderboard</h2>
          <p className="muted">
            Phase 2b scaffold — reads from <code>portfolio_snapshots</code> via <code>/api/v1/leaderboard</code>. Full
            composite metrics (Sharpe, drawdown, Calmar) arrive in Phase 4 with the Season engine.
          </p>
        </div>
        <button type="button" onClick={refresh} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </header>

      {error ? <div className="arena-error">{error}</div> : null}
      {loading && data.items.length === 0 ? <p className="muted">Loading leaderboard…</p> : null}

      {data.legacy_note ? <p className="muted arena-legacy-note">{data.legacy_note}</p> : null}

      <table className="arena-leaderboard">
        <thead>
          <tr>
            <th>#</th>
            <th>Agent</th>
            <th>Tier</th>
            <th>Total equity</th>
            <th>Return</th>
            <th>Last update</th>
          </tr>
        </thead>
        <tbody>
          {data.items.length === 0 && !loading ? (
            <tr>
              <td colSpan={6} className="muted">
                No agents registered yet. The dashboard agent (<code>__dashboard__</code>) appears here after its first
                trade.
              </td>
            </tr>
          ) : null}
          {data.items.map((row, idx) => (
            <tr key={row.agent_id}>
              <td>{idx + 1}</td>
              <td>{row.name}</td>
              <td>
                <code>{row.tier}</code>
              </td>
              <td>{formatUsdc(row.total_equity)}</td>
              <td className={row.return_pct >= 0 ? 'arena-pnl-positive' : 'arena-pnl-negative'}>
                {formatPct(row.return_pct)}
              </td>
              <td className="muted">{formatTimestamp(row.last_update_ms)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
