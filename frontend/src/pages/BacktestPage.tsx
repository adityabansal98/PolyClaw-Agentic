import { useState } from 'react'
import type { BacktestResult, BacktestMetrics, BacktestTrade } from '../lib/types'
import { EquityCurveChart, DrawdownChart, TradePnlChart } from '../components/InteractiveChart'
import { KpiStripEnhanced } from '../components/KpiCardEnhanced'

const API = ''

const STRATEGY_INFO: Record<string, { label: string; tip: string }> = {
  threshold: { label: 'Threshold', tip: 'Buys when price drops below a set level, sells when it rises above another. Simplest strategy.' },
  momentum: { label: 'Momentum', tip: 'Uses moving average crossovers. Buys when short-term trend crosses above long-term, sells on reversal.' },
  mean_reversion: { label: 'Mean Reversion', tip: 'Assumes prices revert to a fair value (default 50%). Buys when price deviates far below, sells when it returns.' },
  kelly_sized: { label: 'Kelly Sized', tip: 'Uses the Kelly Criterion to size each bet based on estimated edge. Quarter-Kelly by default for safety. Larger edge = larger bet.' },
  fade_longshot: { label: 'Fade Longshot', tip: 'Exploits the favorite-longshot bias. Markets overprice longshots (5-10% YES). This strategy buys undervalued positions using calibrated probabilities.' },
  pendulum: { label: 'Pendulum', tip: 'Harvests volatility in evenly-matched markets (35-65% range). Buys dips, sells pops. Profits from price swings regardless of outcome.' },
  nothing_happens: { label: 'Nothing Happens', tip: 'Contrarian fading. 90% of news-driven price spikes revert. Buys crashes and sells when price recovers to pre-spike level.' },
}

function Tip({ text }: { text: string }) {
  return (
    <span className="bt-tip">
      ?
      <span className="bt-tip__popup">{text}</span>
    </span>
  )
}

function formatNum(n: number): string {
  if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(1) + 'K'
  return n.toFixed(0)
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

  const info = STRATEGY_INFO[strategy]

  return (
    <div className="bt-page">
      {/* Config Panel */}
      <div className="bt-config">
        <div className="bt-config__row">
          <div className="bt-field">
            <label>Strategy <Tip text="The trading algorithm to test. Each uses different rules for when to buy and sell." /></label>
            <select value={strategy} onChange={e => setStrategy(e.target.value)}>
              {Object.entries(STRATEGY_INFO).map(([k, v]) => (
                <option key={k} value={k}>{v.label}</option>
              ))}
            </select>
          </div>
          <div className="bt-field bt-field--wide">
            <label>Markets <Tip text="Search for Polymarket bets to test against. E.g. 'NBA' finds NBA Finals markets, 'election' finds political markets." /></label>
            <input type="text" placeholder="e.g. NBA, election, Bitcoin" value={markets}
              onChange={e => setMarkets(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && runBacktest()} />
          </div>
          <div className="bt-field">
            <label>Cash ($) <Tip text="Starting paper money balance. The backtest simulates trading with this amount." /></label>
            <input type="number" value={cash} onChange={e => setCash(Number(e.target.value))} />
          </div>
          <div className="bt-field">
            <label>Fidelity <Tip text="How often price data is sampled. 1 hour = one price point per hour. Lower = more data points but slower." /></label>
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
        {info && <div className="bt-strategy-desc">{info.tip}</div>}
        {error && <div className="bt-error">{error}</div>}
      </div>

      {/* Results */}
      {result && (
        <>
          <KpiStripEnhanced metrics={result.metrics} startingCash={result.starting_cash} />
          <EquityCurveChart curve={result.equity_curve} startingCash={result.starting_cash} trades={result.trades} />
          <DrawdownChart curve={result.equity_curve} />
          <TradePnlChart trades={result.trades} />
          <TradeLog trades={result.trades} />
          <MetricsGrid metrics={result.metrics} result={result} />
        </>
      )}

      {!result && !running && (
        <div className="bt-empty">
          Select a strategy and market query, then click <strong>Run Backtest</strong>
        </div>
      )}
    </div>
  )
}

/* ── Trade Log ── */

function TradeLog({ trades }: { trades: BacktestTrade[] }) {
  if (!trades.length) return null
  return (
    <div className="bt-trades">
      <div className="bt-chart__header">
        <span className="bt-chart__title">Trade Log <Tip text="Every buy and sell the strategy made. BUY = opened a position, SELL = closed it." /></span>
        <span className="bt-chart__range">{trades.length} trades</span>
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
                <td className="bt-reason" title={t.reason}>{t.reason.slice(0, 30)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {trades.length > 50 && <div className="bt-trades__more">Showing first 50 of {trades.length} trades</div>}
      </div>
    </div>
  )
}

/* ── Metrics Grid ── */

const METRIC_TIPS: Record<string, string> = {
  'Strategy': 'The trading algorithm that was tested',
  'Markets': 'Number of Polymarket bets included in this backtest',
  'Starting Cash': 'Initial USDC balance before any trades',
  'Ending Equity': 'Final portfolio value (cash + open positions)',
  'Total Return': 'Percentage gain or loss over the entire backtest period',
  'Sharpe Ratio': 'Return divided by volatility. >1 is good, >2 is excellent',
  'Max Drawdown': 'Largest peak-to-trough decline. Shows worst-case scenario',
  'Win Rate': 'Percentage of round-trip trades that made money',
  'Profit Factor': 'Total profits divided by total losses. >1 means profitable. >2 is strong',
  'Avg Trade PnL': 'Average profit or loss per completed trade',
  'Best Trade': 'Highest single-trade profit',
  'Worst Trade': 'Largest single-trade loss',
  'Total Trades': 'Total number of buy and sell orders executed',
  'W / L': 'Winning trades vs losing trades',
  'Avg Win': 'Average profit on winning trades',
  'Avg Loss': 'Average loss on losing trades',
  'Fees Paid': 'Total transaction fees deducted during the backtest',
  'Fidelity': 'Time interval between price data points used in the simulation',
}

function MetricsGrid({ metrics, result }: { metrics: BacktestMetrics; result: BacktestResult }) {
  const rows: [string, string][] = [
    ['Strategy', result.strategy_name.replace(/_/g, ' ')],
    ['Markets', String(result.markets.length)],
    ['Starting Cash', '$' + formatNum(result.starting_cash)],
    ['Ending Equity', '$' + formatNum(result.ending_equity)],
    ['Total Return', (metrics.total_return_pct >= 0 ? '+' : '') + metrics.total_return_pct.toFixed(2) + '%'],
    ['Sharpe Ratio', metrics.sharpe_ratio?.toFixed(2) ?? 'N/A'],
    ['Max Drawdown', '-' + metrics.max_drawdown_pct.toFixed(2) + '%'],
    ['Win Rate', (metrics.win_rate * 100).toFixed(1) + '%'],
    ['Profit Factor', metrics.profit_factor?.toFixed(2) ?? 'N/A'],
    ['Avg Trade PnL', '$' + metrics.avg_trade_pnl.toFixed(2)],
    ['Best Trade', '$' + metrics.best_trade_pnl.toFixed(2)],
    ['Worst Trade', '$' + metrics.worst_trade_pnl.toFixed(2)],
    ['Total Trades', String(metrics.total_trades)],
    ['W / L', metrics.winning_trades + ' / ' + metrics.losing_trades],
    ['Avg Win', '$' + metrics.avg_win.toFixed(2)],
    ['Avg Loss', '$' + metrics.avg_loss.toFixed(2)],
    ['Fees Paid', '$' + metrics.total_fees_paid.toFixed(2)],
    ['Fidelity', result.fidelity + ' min'],
  ]

  return (
    <div className="bt-metrics">
      <div className="bt-chart__header">
        <span className="bt-chart__title">Performance Summary <Tip text="Detailed breakdown of all performance metrics." /></span>
      </div>
      <div className="bt-metrics__grid">
        {rows.map(([label, value]) => (
          <div key={label}>
            <span>{label} {METRIC_TIPS[label] ? <Tip text={METRIC_TIPS[label]} /> : null}</span>
            <strong style={
              label === 'Best Trade' ? { color: '#3fb950' } :
              label === 'Worst Trade' ? { color: '#f85149' } :
              undefined
            }>{value}</strong>
          </div>
        ))}
      </div>
    </div>
  )
}
