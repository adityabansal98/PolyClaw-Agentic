import { useState } from 'react'
import type { BacktestResult, BacktestMetrics, EquityPoint, BacktestTrade, StrategyInfo } from '../lib/types'

const API = ''

const STRATEGIES = [
  'threshold', 'momentum', 'mean_reversion',
  'kelly_sized', 'fade_longshot', 'pendulum', 'nothing_happens',
]

function formatNum(n: number): string {
  if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(1) + 'K'
  return n.toFixed(0)
}

function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function formatDateTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function BacktestPage() {
  const [strategy, setStrategy] = useState('threshold')
  const [markets, setMarkets] = useState('')
  const [cash, setCash] = useState(10000)
  const [fidelity, setFidelity] = useState(60)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [error, setError] = useState('')

  async function runBacktest() {
    if (!markets.trim()) { setError('Enter a market query'); return }
    setRunning(true)
    setError('')
    setResult(null)

    try {
      const res = await fetch(`${API}/api/backtest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategy, markets: markets.trim(), cash, fidelity, max_markets: 5 }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.error || 'Backtest failed'); return }
      setResult(data)
    } catch (e: any) {
      setError(e.message || 'Network error')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="bt-page">
      {/* Config Panel */}
      <div className="bt-config">
        <div className="bt-config__row">
          <div className="bt-field">
            <label>Strategy</label>
            <select value={strategy} onChange={e => setStrategy(e.target.value)}>
              {STRATEGIES.map(s => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
            </select>
          </div>
          <div className="bt-field bt-field--wide">
            <label>Markets</label>
            <input type="text" placeholder="e.g. NBA, election, Bitcoin" value={markets}
              onChange={e => setMarkets(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && runBacktest()} />
          </div>
          <div className="bt-field">
            <label>Cash ($)</label>
            <input type="number" value={cash} onChange={e => setCash(Number(e.target.value))} />
          </div>
          <div className="bt-field">
            <label>Fidelity</label>
            <select value={fidelity} onChange={e => setFidelity(Number(e.target.value))}>
              <option value={1}>1 min</option>
              <option value={5}>5 min</option>
              <option value={15}>15 min</option>
              <option value={60}>1 hour</option>
              <option value={1440}>Daily</option>
            </select>
          </div>
          <button className="bt-run" onClick={runBacktest} disabled={running}>
            {running ? 'Running...' : 'Run Backtest'}
          </button>
        </div>
        {error && <div className="bt-error">{error}</div>}
      </div>

      {/* Results */}
      {result && (
        <>
          <KpiStrip metrics={result.metrics} startingCash={result.starting_cash} />
          <EquityCurveChart curve={result.equity_curve} />
          <DrawdownChart curve={result.equity_curve} />
          <TradeLog trades={result.trades} />
          <MetricsGrid metrics={result.metrics} result={result} />
        </>
      )}

      {!result && !running && (
        <div className="bt-empty">
          Select a strategy and market query, then click Run Backtest
        </div>
      )}
    </div>
  )
}

function KpiStrip({ metrics, startingCash }: { metrics: BacktestMetrics; startingCash: number }) {
  const returnColor = metrics.total_return_pct >= 0 ? 'var(--kpi-pos)' : 'var(--kpi-neg)'
  return (
    <div className="bt-kpis">
      <div className="bt-kpi">
        <span className="bt-kpi__label">Total Return</span>
        <span className="bt-kpi__value" style={{ color: returnColor }}>
          {metrics.total_return_pct >= 0 ? '+' : ''}{metrics.total_return_pct.toFixed(1)}%
        </span>
        <span className="bt-kpi__sub">${formatNum(metrics.total_return_usd)}</span>
      </div>
      <div className="bt-kpi">
        <span className="bt-kpi__label">Sharpe Ratio</span>
        <span className="bt-kpi__value">{metrics.sharpe_ratio?.toFixed(2) ?? 'N/A'}</span>
      </div>
      <div className="bt-kpi">
        <span className="bt-kpi__label">Max Drawdown</span>
        <span className="bt-kpi__value" style={{ color: 'var(--kpi-neg)' }}>
          -{metrics.max_drawdown_pct.toFixed(1)}%
        </span>
      </div>
      <div className="bt-kpi">
        <span className="bt-kpi__label">Win Rate</span>
        <span className="bt-kpi__value">{(metrics.win_rate * 100).toFixed(0)}%</span>
        <span className="bt-kpi__sub">{metrics.total_trades} trades</span>
      </div>
    </div>
  )
}

function EquityCurveChart({ curve }: { curve: EquityPoint[] }) {
  if (curve.length < 2) return null
  const maxEquity = Math.max(...curve.map(p => p.total_equity))
  const minEquity = Math.min(...curve.map(p => p.total_equity))
  const range = maxEquity - minEquity || 1
  const w = 800
  const h = 200
  const points = curve.map((p, i) => {
    const x = (i / (curve.length - 1)) * w
    const y = h - ((p.total_equity - minEquity) / range) * h
    return `${x},${y}`
  }).join(' ')

  return (
    <div className="bt-chart">
      <div className="bt-chart__header">
        <span className="bt-chart__title">Equity Curve</span>
        <span className="bt-chart__range">${formatNum(minEquity)} - ${formatNum(maxEquity)}</span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} className="bt-chart__svg">
        <polyline points={points} fill="none" stroke="#3fb950" strokeWidth="2" />
      </svg>
      <div className="bt-chart__labels">
        <span>{formatDate(curve[0].timestamp)}</span>
        <span>{formatDate(curve[curve.length - 1].timestamp)}</span>
      </div>
    </div>
  )
}

function DrawdownChart({ curve }: { curve: EquityPoint[] }) {
  if (curve.length < 2) return null
  let peak = curve[0].total_equity
  const drawdowns = curve.map(p => {
    if (p.total_equity > peak) peak = p.total_equity
    return peak > 0 ? -((peak - p.total_equity) / peak) * 100 : 0
  })
  const maxDD = Math.min(...drawdowns)
  const range = Math.abs(maxDD) || 1
  const w = 800
  const h = 100
  const points = drawdowns.map((dd, i) => {
    const x = (i / (drawdowns.length - 1)) * w
    const y = (Math.abs(dd) / range) * h
    return `${x},${y}`
  }).join(' ')

  return (
    <div className="bt-chart bt-chart--dd">
      <div className="bt-chart__header">
        <span className="bt-chart__title">Drawdown</span>
        <span className="bt-chart__range">Max: {maxDD.toFixed(1)}%</span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} className="bt-chart__svg">
        <polyline points={`0,0 ${points} ${w},0`} fill="rgba(248,81,73,0.15)" stroke="#f85149" strokeWidth="1.5" />
      </svg>
    </div>
  )
}

function TradeLog({ trades }: { trades: BacktestTrade[] }) {
  if (!trades.length) return null
  return (
    <div className="bt-trades">
      <div className="bt-chart__header">
        <span className="bt-chart__title">Trade Log ({trades.length} trades)</span>
      </div>
      <div className="bt-trades__scroll">
        <table className="bt-trades__table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Market</th>
              <th>Side</th>
              <th>Price</th>
              <th>Shares</th>
              <th>Cost</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {trades.slice(0, 50).map((t, i) => (
              <tr key={i}>
                <td>{formatDateTime(t.timestamp)}</td>
                <td title={t.market_question}>{t.market_question.slice(0, 35)}</td>
                <td><span className={`bt-side bt-side--${t.side.toLowerCase()}`}>{t.side}</span></td>
                <td>${t.price.toFixed(4)}</td>
                <td>{formatNum(t.shares)}</td>
                <td>${t.cost.toFixed(2)}</td>
                <td className="bt-reason">{t.reason.slice(0, 30)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {trades.length > 50 && <div className="bt-trades__more">Showing first 50 of {trades.length} trades</div>}
      </div>
    </div>
  )
}

function MetricsGrid({ metrics, result }: { metrics: BacktestMetrics; result: BacktestResult }) {
  return (
    <div className="bt-metrics">
      <div className="bt-chart__header">
        <span className="bt-chart__title">Performance Summary</span>
      </div>
      <div className="bt-metrics__grid">
        <div><span>Strategy</span><strong>{result.strategy_name}</strong></div>
        <div><span>Markets</span><strong>{result.markets.length}</strong></div>
        <div><span>Starting Cash</span><strong>${formatNum(result.starting_cash)}</strong></div>
        <div><span>Ending Equity</span><strong>${formatNum(result.ending_equity)}</strong></div>
        <div><span>Total Return</span><strong>{metrics.total_return_pct >= 0 ? '+' : ''}{metrics.total_return_pct.toFixed(2)}%</strong></div>
        <div><span>Sharpe Ratio</span><strong>{metrics.sharpe_ratio?.toFixed(2) ?? 'N/A'}</strong></div>
        <div><span>Max Drawdown</span><strong>-{metrics.max_drawdown_pct.toFixed(2)}%</strong></div>
        <div><span>Win Rate</span><strong>{(metrics.win_rate * 100).toFixed(1)}%</strong></div>
        <div><span>Profit Factor</span><strong>{metrics.profit_factor?.toFixed(2) ?? 'N/A'}</strong></div>
        <div><span>Avg Trade PnL</span><strong>${metrics.avg_trade_pnl.toFixed(2)}</strong></div>
        <div><span>Best Trade</span><strong style={{color: '#3fb950'}}>${metrics.best_trade_pnl.toFixed(2)}</strong></div>
        <div><span>Worst Trade</span><strong style={{color: '#f85149'}}>${metrics.worst_trade_pnl.toFixed(2)}</strong></div>
        <div><span>Total Trades</span><strong>{metrics.total_trades}</strong></div>
        <div><span>W / L</span><strong>{metrics.winning_trades} / {metrics.losing_trades}</strong></div>
        <div><span>Avg Win</span><strong>${metrics.avg_win.toFixed(2)}</strong></div>
        <div><span>Avg Loss</span><strong>${metrics.avg_loss.toFixed(2)}</strong></div>
        <div><span>Fees Paid</span><strong>${metrics.total_fees_paid.toFixed(2)}</strong></div>
        <div><span>Fidelity</span><strong>{result.fidelity} min</strong></div>
      </div>
    </div>
  )
}
