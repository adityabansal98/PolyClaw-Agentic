// Phase 6 — Leaderboard with composite metrics, sortable columns, agent drill-down.
// Demo mode: renders mock data when ?demo=hw6|hw7|hw8 is in URL.
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getDemoVersion } from '../lib/demoMode'
import { getDemoAgents, type LeaderboardRow } from '../lib/demoData'

type SortKey = keyof LeaderboardRow

function fmtUsd(n: number) {
  return '$' + n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(n: number | null, decimals = 2) {
  if (n === null) return 'N/A'
  const pct = typeof n === 'number' && Math.abs(n) < 10 ? n * 100 : n
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(decimals)}%`
}

export function LeaderboardPage() {
  const [rows, setRows] = useState<LeaderboardRow[]>([])
  const [loading, setLoading] = useState(true)
  const [sortKey, setSortKey] = useState<SortKey>('rank')
  const [sortAsc, setSortAsc] = useState(true)
  const [tierFilter, setTierFilter] = useState<string>('all')
  const version = getDemoVersion()

  useEffect(() => {
    if (version) {
      setRows(getDemoAgents(version))
      setLoading(false)
      return
    }
    fetch('/api/v1/leaderboard')
      .then(r => r.json())
      .then(data => {
        const items = (data.items || []).map((r: LeaderboardRow, i: number) => ({
          ...r,
          rank: r.rank || i + 1,
        }))
        setRows(items)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [version])

  const filtered = tierFilter === 'all' ? rows : rows.filter(r => r.tier === tierFilter)

  const sorted = [...filtered].sort((a, b) => {
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

  const tiers = [...new Set(rows.map(r => r.tier))]

  return (
    <div className="leaderboard-page">
      <h1>Leaderboard</h1>
      <p className="muted">Ranked by composite score (35% return, 25% Sharpe, 15% DD, 10% Calmar, 10% win rate, 5% trades).</p>

      {/* Tier filter for hw8 */}
      {version === 'hw8' && (
        <div className="tier-filter">
          <button className={tierFilter === 'all' ? 'active' : ''} onClick={() => setTierFilter('all')}>All ({rows.length})</button>
          {tiers.map(t => (
            <button key={t} className={tierFilter === t ? 'active' : ''} onClick={() => setTierFilter(t)}>
              {t} ({rows.filter(r => r.tier === t).length})
            </button>
          ))}
        </div>
      )}

      {loading ? <p className="muted">Loading...</p> : (
        <table className="arena-leaderboard">
          <thead>
            <tr>
              <SortHeader label="#" field="rank" />
              <SortHeader label="Agent" field="name" />
              <th>Tier</th>
              {(version === 'hw7' || version === 'hw8') && <th>Strategy</th>}
              {version === 'hw8' && <th>Status</th>}
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
              <tr key={r.agent_id} className={r.status === 'paused' ? 'row-paused' : ''}>
                <td>{r.rank}</td>
                <td><Link to={`/agents/${r.agent_id}${version ? `?demo=${version}` : ''}`}>{r.name}</Link></td>
                <td><code>{r.tier}</code></td>
                {(version === 'hw7' || version === 'hw8') && <td><code>{r.strategy || '-'}</code></td>}
                {version === 'hw8' && (
                  <td>
                    {r.status === 'paused'
                      ? <span className="status-pill status-pill--paused" title={r.pause_reason}>PAUSED</span>
                      : <span className="status-pill status-pill--active">ACTIVE</span>
                    }
                  </td>
                )}
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
