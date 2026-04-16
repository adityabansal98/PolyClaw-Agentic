import type { BacktestMetrics } from '../lib/types'

/* ── helpers ── */
function fmtUsd(n: number) {
  if (Math.abs(n) >= 1e6) return '$' + (n / 1e6).toFixed(1) + 'M'
  if (Math.abs(n) >= 1e3) return '$' + (n / 1e3).toFixed(1) + 'K'
  return '$' + n.toFixed(0)
}

/* ── Enhanced KPI Strip ── */

interface Props {
  metrics: BacktestMetrics
  startingCash: number
}

export function KpiStripEnhanced({ metrics, startingCash: _startingCash }: Props) {
  const returnColor = metrics.total_return_pct >= 0 ? '#3fb950' : '#f85149'
  const sharpe = metrics.sharpe_ratio

  // Sharpe rating
  let sharpeColor = '#f85149'
  let sharpeLabel = 'Poor'
  if (sharpe !== null) {
    if (sharpe >= 2) { sharpeColor = '#f5b13f'; sharpeLabel = 'Excellent' }
    else if (sharpe >= 1) { sharpeColor = '#3fb950'; sharpeLabel = 'Good' }
    else if (sharpe >= 0) { sharpeColor = '#d29922'; sharpeLabel = 'OK' }
    else { sharpeColor = '#f85149'; sharpeLabel = 'Poor' }
  }

  // Win/Loss bar
  const wins = metrics.winning_trades
  const losses = metrics.losing_trades
  const total = wins + losses
  const winPct = total > 0 ? (wins / total) * 100 : 0

  // Profit factor plain English
  const pf = metrics.profit_factor
  const pfText = pf !== null ? `$1 lost → $${pf.toFixed(2)} earned` : 'N/A'

  return (
    <div className="bt-kpis-enhanced">
      {/* Total Return */}
      <div className="bt-kpi-e">
        <span className="bt-kpi-e__label">Total Return</span>
        <span className="bt-kpi-e__value" style={{ color: returnColor }}>
          {metrics.total_return_pct >= 0 ? '+' : ''}{metrics.total_return_pct.toFixed(1)}%
        </span>
        <span className="bt-kpi-e__context">{fmtUsd(metrics.total_return_usd)}</span>
      </div>

      {/* Sharpe Ratio */}
      <div className="bt-kpi-e">
        <span className="bt-kpi-e__label">Sharpe Ratio</span>
        <span className="bt-kpi-e__value">{sharpe?.toFixed(2) ?? 'N/A'}</span>
        <div className="bt-kpi-e__bar-wrap">
          <div className="bt-kpi-e__bar">
            <div className="bt-kpi-e__bar-zone bt-kpi-e__bar-zone--red" style={{ width: '25%' }} />
            <div className="bt-kpi-e__bar-zone bt-kpi-e__bar-zone--yellow" style={{ width: '25%' }} />
            <div className="bt-kpi-e__bar-zone bt-kpi-e__bar-zone--green" style={{ width: '25%' }} />
            <div className="bt-kpi-e__bar-zone bt-kpi-e__bar-zone--gold" style={{ width: '25%' }} />
            {sharpe !== null && (
              <div
                className="bt-kpi-e__bar-marker"
                style={{ left: `${Math.min(Math.max((sharpe + 1) / 4 * 100, 0), 100)}%` }}
              />
            )}
          </div>
          <span className="bt-kpi-e__badge" style={{ color: sharpeColor }}>{sharpeLabel}</span>
        </div>
      </div>

      {/* Max Drawdown */}
      <div className="bt-kpi-e">
        <span className="bt-kpi-e__label">Max Drawdown</span>
        <span className="bt-kpi-e__value" style={{ color: '#f85149' }}>
          -{metrics.max_drawdown_pct.toFixed(1)}%
        </span>
        <span className="bt-kpi-e__context">{fmtUsd(metrics.max_drawdown_usd)}</span>
      </div>

      {/* Win Rate */}
      <div className="bt-kpi-e">
        <span className="bt-kpi-e__label">Win Rate</span>
        <span className="bt-kpi-e__value">{(metrics.win_rate * 100).toFixed(0)}%</span>
        <div className="bt-kpi-e__winloss">
          <div className="bt-kpi-e__winloss-bar">
            <div className="bt-kpi-e__winloss-fill bt-kpi-e__winloss-fill--win" style={{ width: `${winPct}%` }} />
            <div className="bt-kpi-e__winloss-fill bt-kpi-e__winloss-fill--loss" style={{ width: `${100 - winPct}%` }} />
          </div>
          <span className="bt-kpi-e__context">{wins}W / {losses}L</span>
        </div>
      </div>

      {/* Profit Factor */}
      <div className="bt-kpi-e">
        <span className="bt-kpi-e__label">Profit Factor</span>
        <span className="bt-kpi-e__value">{pf?.toFixed(2) ?? 'N/A'}</span>
        <span className="bt-kpi-e__context">{pfText}</span>
      </div>

      {/* Total Trades */}
      <div className="bt-kpi-e">
        <span className="bt-kpi-e__label">Total Trades</span>
        <span className="bt-kpi-e__value">{metrics.total_trades}</span>
        <span className="bt-kpi-e__context">
          Avg PnL: {metrics.avg_trade_pnl >= 0 ? '+' : ''}{fmtUsd(metrics.avg_trade_pnl)}
        </span>
      </div>
    </div>
  )
}
