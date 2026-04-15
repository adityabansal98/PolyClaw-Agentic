import { useEffect, useState } from 'react'

type ArenaLeaderboardRow = {
  agent: string
  balance: number
  realized_pnl: number
  total_pnl: number
}

type ArenaTickerRow = {
  event_type: string
  message: string
  created_at: string
}

type ArenaMarketRow = {
  market_id: string
  question: string
  market_url?: string | null
  side: 'YES' | 'NO'
  p_model_yes: number
  p_market_yes: number
  score: number
  confidence: number
  expected_value: number
}

type ArenaState = {
  generated_at: string | null
  starting_balance: number
  leaderboard: ArenaLeaderboardRow[]
  ticker: ArenaTickerRow[]
  active_bets: Array<{
    agent_name: string
    market_id: string
    question: string
    side: 'YES' | 'NO'
    stake: number
    shares: number
    entry_price: number
    opened_at: string
  }>
  markets: ArenaMarketRow[]
  message?: string
}

type ArenaBetRow = {
  agent_name: string
  market_id: string
  question: string
  side: 'YES' | 'NO'
  stake: number
  shares: number
  entry_price: number
  opened_at: string
  settled_at?: string | null
  exit_price?: number | null
  pnl?: number | null
  status?: string
}

const EMPTY_STATE: ArenaState = {
  generated_at: null,
  starting_balance: 1000,
  leaderboard: [],
  ticker: [],
  active_bets: [],
  markets: [],
}

export function AgentArenaPage() {
  const [state, setState] = useState<ArenaState>(EMPTY_STATE)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedMarketId, setSelectedMarketId] = useState<string | null>(null)
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null)
  const [marketActivity, setMarketActivity] = useState<ArenaBetRow[]>([])
  const [agentActivity, setAgentActivity] = useState<ArenaBetRow[]>([])

  async function refresh() {
    try {
      const response = await fetch('/api/arena/state')
      const payload = (await response.json()) as ArenaState | { error?: string }
      if (!response.ok) {
        const message = 'error' in payload && payload.error ? payload.error : `Request failed: ${response.status}`
        throw new Error(message)
      }
      setState(payload as ArenaState)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load AgentArena state.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
    const id = window.setInterval(() => {
      void refresh()
    }, 8000)
    return () => window.clearInterval(id)
  }, [])

  useEffect(() => {
    if (selectedMarketId) {
      return
    }
    if (state.markets.length > 0) {
      setSelectedMarketId(state.markets[0].market_id)
    }
  }, [state.markets, selectedMarketId])

  useEffect(() => {
    if (selectedAgent) {
      return
    }
    if (state.leaderboard.length > 0) {
      setSelectedAgent(state.leaderboard[0].agent)
    }
  }, [state.leaderboard, selectedAgent])

  useEffect(() => {
    if (!selectedMarketId) {
      setMarketActivity([])
      return
    }
    let isMounted = true
    const load = async () => {
      try {
        const response = await fetch(`/api/arena/market/${selectedMarketId}/bets`)
        const payload = (await response.json()) as { items?: ArenaBetRow[] }
        if (isMounted) {
          setMarketActivity(payload.items ?? [])
        }
      } catch {
        if (isMounted) {
          setMarketActivity([])
        }
      }
    }
    void load()
    return () => {
      isMounted = false
    }
  }, [selectedMarketId])

  useEffect(() => {
    if (!selectedAgent) {
      setAgentActivity([])
      return
    }
    let isMounted = true
    const load = async () => {
      try {
        const response = await fetch(`/api/arena/agent/${encodeURIComponent(selectedAgent)}/bets`)
        const payload = (await response.json()) as { items?: ArenaBetRow[] }
        if (isMounted) {
          setAgentActivity(payload.items ?? [])
        }
      } catch {
        if (isMounted) {
          setAgentActivity([])
        }
      }
    }
    void load()
    return () => {
      isMounted = false
    }
  }, [selectedAgent])

  return (
    <div className="page-stack">
      <div className="panel">
        <div className="panel__header">
          <div>
            <h2>AgentArena</h2>
            <p className="panel__subtitle">
              Multi-agent NBA paper simulation with hourly price-move settlement.
            </p>
          </div>
          <button className="button button--ghost" type="button" onClick={() => void refresh()}>
            Refresh
          </button>
        </div>
        {state.message ? <p className="muted">{state.message}</p> : null}
        {error ? <p className="muted">{error}</p> : null}
        {loading ? <p className="muted">Loading AgentArena state...</p> : null}
        <div className="arena-meta">
          <span>Starting balance: {state.starting_balance.toFixed(2)} coins</span>
          <span>Last update: {state.generated_at ?? 'N/A'}</span>
          <span>Open bets: {state.active_bets.length}</span>
        </div>
      </div>

      <div className="overview-grid">
        <div className="panel">
          <div className="panel__header">
            <h3>Agent Leaderboard</h3>
          </div>
          <div className="table-shell">
            <table>
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Balance</th>
                  <th>Total PnL</th>
                  <th>Realized PnL</th>
                </tr>
              </thead>
              <tbody>
                {state.leaderboard.map((row) => (
                  <tr key={row.agent}>
                    <td>{row.agent}</td>
                    <td>{row.balance.toFixed(2)}</td>
                    <td>{row.total_pnl.toFixed(2)}</td>
                    <td>{row.realized_pnl.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="panel">
          <div className="panel__header">
            <h3>Live Agent Ticker</h3>
          </div>
          <div className="arena-ticker">
            {state.ticker.map((event, idx) => (
              <div className="arena-ticker__row" key={`${event.created_at}-${idx}`}>
                <span className="arena-ticker__time">{new Date(event.created_at).toLocaleTimeString()}</span>
                <span>{event.message}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel__header">
          <h3>NBA Market View (Fair vs Market)</h3>
        </div>
        <div className="table-shell">
          <table className="clickable-table">
            <thead>
              <tr>
                <th>Market</th>
                <th>Link</th>
                <th>Side</th>
                <th>Fair Price</th>
                <th>Market Price</th>
                <th>Score</th>
                <th>Confidence</th>
                <th>EV</th>
              </tr>
            </thead>
            <tbody>
              {state.markets.map((market) => (
                <tr
                  key={market.market_id}
                  className={selectedMarketId === market.market_id ? 'is-selected' : ''}
                  onClick={() => {
                    setSelectedMarketId(market.market_id)
                    if (market.market_url) {
                      window.open(market.market_url, '_blank', 'noopener,noreferrer')
                    }
                  }}
                >
                  <td>{market.question}</td>
                  <td>
                    {market.market_url ? (
                      <a
                        href={market.market_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="arena-market-link"
                        onClick={(event) => event.stopPropagation()}
                      >
                        Polymarket
                      </a>
                    ) : (
                      <span className="muted">N/A</span>
                    )}
                  </td>
                  <td>{market.side}</td>
                  <td>{(market.p_model_yes * 100).toFixed(2)}%</td>
                  <td>{(market.p_market_yes * 100).toFixed(2)}%</td>
                  <td>{market.score.toFixed(3)}</td>
                  <td>{market.confidence.toFixed(3)}</td>
                  <td>{market.expected_value.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <div className="panel__header">
          <h3>Market Bet Breakdown</h3>
          <span className="muted">{selectedMarketId ? `Market ${selectedMarketId}` : 'Select a market above'}</span>
        </div>
        <div className="table-shell">
          <table>
            <thead>
              <tr>
                <th>Agent</th>
                <th>Side</th>
                <th>Stake</th>
                <th>Shares</th>
                <th>Entry Price</th>
                <th>Opened</th>
              </tr>
            </thead>
            <tbody>
              {marketActivity.length === 0 ? (
                <tr>
                  <td colSpan={6} className="muted">
                    No active bets for this market yet.
                  </td>
                </tr>
              ) : (
                marketActivity.map((bet, idx) => (
                  <tr key={`${bet.agent_name}-${bet.market_id}-${bet.opened_at}-${idx}`}>
                    <td>{bet.agent_name}</td>
                    <td>{bet.side}</td>
                    <td>{bet.stake.toFixed(2)}</td>
                    <td>{bet.shares.toFixed(2)}</td>
                    <td>{(bet.entry_price * 100).toFixed(2)}%</td>
                    <td>{new Date(bet.opened_at).toLocaleString()}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <div className="panel__header">
          <h3>Agent Activity</h3>
          <select
            className="opp-sort-select"
            value={selectedAgent ?? ''}
            onChange={(event) => setSelectedAgent(event.target.value || null)}
          >
            {state.leaderboard.map((row) => (
              <option key={row.agent} value={row.agent}>
                {row.agent}
              </option>
            ))}
          </select>
        </div>
        <div className="table-shell">
          <table>
            <thead>
              <tr>
                <th>Market</th>
                <th>Side</th>
                <th>Stake</th>
                <th>Status</th>
                <th>PnL</th>
                <th>Opened</th>
              </tr>
            </thead>
            <tbody>
              {agentActivity.length === 0 ? (
                <tr>
                  <td colSpan={6} className="muted">
                    No bets found for this agent yet.
                  </td>
                </tr>
              ) : (
                agentActivity.map((bet, idx) => (
                  <tr key={`${bet.market_id}-${bet.opened_at}-${idx}`}>
                    <td>{bet.question}</td>
                    <td>{bet.side}</td>
                    <td>{Number(bet.stake).toFixed(2)}</td>
                    <td>{(bet.status ?? 'OPEN').toUpperCase()}</td>
                    <td>{bet.pnl == null ? '-' : Number(bet.pnl).toFixed(2)}</td>
                    <td>{new Date(bet.opened_at).toLocaleString()}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
