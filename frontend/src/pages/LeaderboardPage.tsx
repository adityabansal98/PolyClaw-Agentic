// Phase 6 — Leaderboard with composite metrics, sortable columns, agent drill-down.
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

type LeaderboardRow = {
  rank: number
  agent_id: string
  name: string
  tier: string
  total_equity: number
  return_pct: number  // already as decimal, e.g. 0.05 = 5%
  sharpe: number | null
  max_drawdown: number
  calmar: number | null
  win_rate: number
  trade_count: number
}

type SortKey = keyof LeaderboardRow

function fmtUsd(n: number) {
  return '$' + n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(n: number | null, decimals = 2) {
  if (n === null) return 'N/A'
  const pct = typeof n === 'number' && Math.abs(n) < 10 ? n * 100 : n  // handle both decimal and pct
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(decimals)}%`
}

export function LeaderboardPage() {
  const [rows, setRows] = useState<LeaderboardRow[]>([])
  const [loading, setLoading] = useState(true)
  const [sortKey, setSortKey] = useState<SortKey>('rank')
  const [sortAsc, setSortAsc] = useState(true)

  useEffect(() => {
    fetch('/api/v1/leaderboard')
      .then(r => r.json())
      .then(data => {
        // The leaderboard endpoint may return items without rank if using the old
        // endpoint; the new /api/v1/seasons/:id/results includes rank. Fall back.
        const items = (data.items || []).map((r: LeaderboardRow, i: number) => ({
          ...r,
          rank: r.rank || i + 1,
        }))
        setRows(items)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const sorted = [...rows].sort((a, b) => {
    const av = a[sortKey] ?? -Infinity
    const bv = b[sortKey] ?? -Infinity
    return sortAsc ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1)
  })

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortAsc(!sortAsc)
    else { setSortKey(key); setSortAsc(key === 'rank') }
  }

  function SortHeader({ label, field }: { label: string; field: SortKey }) {
    const arrow = sortKey === field ? (sortAsc ? ' \u25B2' : ' \u25BC') : ''
    return <th onClick={() => toggleSort(field)} style={{ cursor: 'pointer' }}>{label}{arrow}</th>
  }

  return (
    <div className="leaderboard-page">
      <h1>Leaderboard</h1>
      <p className="muted">Ranked by composite score (35% return, 25% Sharpe, 15% DD, 10% Calmar, 10% win rate, 5% trades).</p>

      {loading ? <p className="muted">Loading...</p> : (
        <table className="arena-leaderboard">
          <thead>
            <tr>
              <SortHeader label="#" field="rank" />
              <SortHeader label="Agent" field="name" />
              <th>Tier</th>
              <SortHeader label="Equity" field="total_equity" />
              <SortHeader label="Return" field="return_pct" />
              <SortHeader label="Sharpe" field="sharpe" />
              <SortHeader label="Max DD" field="max_drawdown" />
              <SortHeader label="Calmar" field="calmar" />
              <SortHeader label="Win Rate" field="win_rate" />
              <SortHeader label="Trades" field="trade_count" />
            </tr>
          </thead>
          <tbody>
            {sorted.map(r => (
              <tr key={r.agent_id}>
                <td>{r.rank}</td>
                <td><Link to={`/agents/${r.agent_id}`}>{r.name}</Link></td>
                <td><code>{r.tier}</code></td>
                <td>{fmtUsd(r.total_equity)}</td>
                <td className={r.return_pct >= 0 ? 'arena-pnl-positive' : 'arena-pnl-negative'}>
                  {fmtPct(r.return_pct)}
                </td>
                <td>{r.sharpe?.toFixed(2) ?? 'N/A'}</td>
                <td className="arena-pnl-negative">{r.max_drawdown ? `-${(r.max_drawdown * 100).toFixed(2)}%` : '0%'}</td>
                <td>{r.calmar?.toFixed(2) ?? 'N/A'}</td>
                <td>{(r.win_rate * 100).toFixed(1)}%</td>
                <td>{r.trade_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
