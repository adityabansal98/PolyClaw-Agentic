import {
  LineChart, Line, AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceLine, Cell,
} from 'recharts'
import type { EquityPoint, BacktestTrade } from '../lib/types'

/* ── helpers ── */

function fmtDate(ts: number) {
  return new Date(ts * 1000).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}
function fmtDateTime(ts: number) {
  return new Date(ts * 1000).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
function fmtUsd(n: number) {
  if (Math.abs(n) >= 1e6) return '$' + (n / 1e6).toFixed(1) + 'M'
  if (Math.abs(n) >= 1e3) return '$' + (n / 1e3).toFixed(1) + 'K'
  return '$' + n.toFixed(0)
}
function fmtPct(n: number) {
  return (n >= 0 ? '+' : '') + n.toFixed(2) + '%'
}

/* ── Equity Curve ── */

interface EquityCurveProps {
  curve: EquityPoint[]
  startingCash: number
  trades: BacktestTrade[]
}

export function EquityCurveChart({ curve, startingCash, trades }: EquityCurveProps) {
  if (curve.length < 2) return null

  // build data with benchmark (buy-and-hold)
  const firstEquity = curve[0].total_equity
  const data = curve.map((p) => {
    const benchmarkRatio = firstEquity > 0 ? startingCash * (p.total_equity / firstEquity) : startingCash
    return {
      ts: p.timestamp,
      date: fmtDate(p.timestamp),
      equity: +p.total_equity.toFixed(2),
      benchmark: +benchmarkRatio.toFixed(2),
      returnPct: +( ((p.total_equity - startingCash) / startingCash) * 100 ).toFixed(2),
    }
  })

  // trade markers on the equity curve
  const buyMarkers: { ts: number; equity: number; question: string }[] = []
  const sellMarkers: { ts: number; equity: number; question: string }[] = []
  trades.forEach((t) => {
    // find closest equity point
    const ep = curve.reduce((best, p) =>
      Math.abs(p.timestamp - t.timestamp) < Math.abs(best.timestamp - t.timestamp) ? p : best
    )
    const marker = { ts: t.timestamp, equity: ep.total_equity, question: t.market_question }
    if (t.side === 'BUY') buyMarkers.push(marker)
    else sellMarkers.push(marker)
  })

  return (
    <div className="bt-chart">
      <div className="bt-chart__header">
        <span className="bt-chart__title">Equity Curve</span>
        <span className="bt-chart__range">{fmtUsd(data[0].equity)} → {fmtUsd(data[data.length - 1].equity)}</span>
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={data} margin={{ top: 10, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
          <XAxis
            dataKey="date"
            tick={{ fill: 'rgba(255,255,255,0.35)', fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: 'rgba(255,255,255,0.08)' }}
            interval="preserveStartEnd"
            minTickGap={60}
          />
          <YAxis
            tickFormatter={(v: number) => fmtUsd(v)}
            tick={{ fill: 'rgba(255,255,255,0.35)', fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={65}
          />
          <Tooltip
            contentStyle={{
              background: '#1a1f2b',
              border: '1px solid rgba(255,255,255,0.15)',
              borderRadius: 8,
              fontSize: 12,
              color: '#e6edf3',
            }}
            labelFormatter={(label: string) => label}
            formatter={(value: number, name: string) => {
              if (name === 'equity') return [fmtUsd(value), 'Portfolio']
              if (name === 'benchmark') return [fmtUsd(value), 'Buy & Hold']
              return [value, name]
            }}
          />
          <ReferenceLine y={startingCash} stroke="rgba(255,255,255,0.15)" strokeDasharray="4 4" label="" />
          <Line
            type="monotone"
            dataKey="equity"
            stroke="#3fb950"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: '#3fb950' }}
          />
          <Line
            type="monotone"
            dataKey="benchmark"
            stroke="rgba(255,255,255,0.2)"
            strokeWidth={1}
            strokeDasharray="5 5"
            dot={false}
            activeDot={{ r: 3, fill: 'rgba(255,255,255,0.3)' }}
          />
        </LineChart>
      </ResponsiveContainer>
      <div className="bt-chart__legend">
        <span className="bt-chart__legend-item"><span style={{ background: '#3fb950' }} className="bt-chart__dot" /> Portfolio</span>
        <span className="bt-chart__legend-item"><span style={{ background: 'rgba(255,255,255,0.3)' }} className="bt-chart__dot" /> Buy & Hold</span>
      </div>
    </div>
  )
}

/* ── Drawdown Chart ── */

interface DrawdownProps {
  curve: EquityPoint[]
}

export function DrawdownChart({ curve }: DrawdownProps) {
  if (curve.length < 2) return null

  let peak = curve[0].total_equity
  const data = curve.map((p) => {
    if (p.total_equity > peak) peak = p.total_equity
    const dd = peak > 0 ? -((peak - p.total_equity) / peak) * 100 : 0
    return {
      date: fmtDate(p.timestamp),
      ts: p.timestamp,
      drawdown: +dd.toFixed(2),
    }
  })

  const maxDD = Math.min(...data.map(d => d.drawdown))

  return (
    <div className="bt-chart bt-chart--dd">
      <div className="bt-chart__header">
        <span className="bt-chart__title">Drawdown</span>
        <span className="bt-chart__range">Max: {maxDD.toFixed(1)}%</span>
      </div>
      <ResponsiveContainer width="100%" height={140}>
        <AreaChart data={data} margin={{ top: 5, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
          <XAxis
            dataKey="date"
            tick={{ fill: 'rgba(255,255,255,0.35)', fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: 'rgba(255,255,255,0.08)' }}
            interval="preserveStartEnd"
            minTickGap={60}
          />
          <YAxis
            tickFormatter={(v: number) => v.toFixed(0) + '%'}
            tick={{ fill: 'rgba(255,255,255,0.35)', fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={45}
            domain={['dataMin', 0]}
          />
          <Tooltip
            contentStyle={{
              background: '#1a1f2b',
              border: '1px solid rgba(255,255,255,0.15)',
              borderRadius: 8,
              fontSize: 12,
              color: '#e6edf3',
            }}
            formatter={(value: number) => [value.toFixed(2) + '%', 'Drawdown']}
          />
          <ReferenceLine y={0} stroke="rgba(255,255,255,0.1)" />
          <Area
            type="monotone"
            dataKey="drawdown"
            stroke="#f85149"
            fill="rgba(248,81,73,0.15)"
            strokeWidth={1.5}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

/* ── Per-Trade PnL Bar Chart ── */

interface TradePnlProps {
  trades: BacktestTrade[]
}

interface RoundTrip {
  question: string
  entryPrice: number
  exitPrice: number
  shares: number
  pnl: number
  holdingPeriod: string
  entryTime: string
  exitTime: string
}

export function TradePnlChart({ trades }: TradePnlProps) {
  if (trades.length < 2) return null

  // pair up BUY → SELL round-trips
  const roundTrips: RoundTrip[] = []
  const openTrades: Record<string, BacktestTrade> = {}

  for (const t of trades) {
    const key = t.token_id
    if (t.side === 'BUY') {
      openTrades[key] = t
    } else if (t.side === 'SELL' && openTrades[key]) {
      const entry = openTrades[key]
      const pnl = (t.price - entry.price) * entry.shares - entry.fee - t.fee
      const holdSecs = t.timestamp - entry.timestamp
      const hours = holdSecs / 3600
      roundTrips.push({
        question: t.market_question.slice(0, 40),
        entryPrice: entry.price,
        exitPrice: t.price,
        shares: entry.shares,
        pnl: +pnl.toFixed(2),
        holdingPeriod: hours < 1 ? `${(hours * 60).toFixed(0)}m` : hours < 24 ? `${hours.toFixed(1)}h` : `${(hours / 24).toFixed(1)}d`,
        entryTime: fmtDateTime(entry.timestamp),
        exitTime: fmtDateTime(t.timestamp),
      })
      delete openTrades[key]
    }
  }

  if (roundTrips.length === 0) return null

  const data = roundTrips.map((rt, i) => ({
    idx: i + 1,
    pnl: rt.pnl,
    question: rt.question,
    entry: rt.entryPrice,
    exit: rt.exitPrice,
    held: rt.holdingPeriod,
    entryTime: rt.entryTime,
    exitTime: rt.exitTime,
  }))

  return (
    <div className="bt-chart">
      <div className="bt-chart__header">
        <span className="bt-chart__title">Per-Trade PnL</span>
        <span className="bt-chart__range">{roundTrips.length} round-trips</span>
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={data} margin={{ top: 5, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
          <XAxis
            dataKey="idx"
            tick={{ fill: 'rgba(255,255,255,0.35)', fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: 'rgba(255,255,255,0.08)' }}
            label={{ value: 'Trade #', position: 'insideBottom', offset: -2, fill: 'rgba(255,255,255,0.3)', fontSize: 10 }}
          />
          <YAxis
            tickFormatter={(v: number) => fmtUsd(v)}
            tick={{ fill: 'rgba(255,255,255,0.35)', fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={55}
          />
          <Tooltip
            contentStyle={{
              background: '#1a1f2b',
              border: '1px solid rgba(255,255,255,0.15)',
              borderRadius: 8,
              fontSize: 12,
              color: '#e6edf3',
            }}
            formatter={(value: number) => [fmtUsd(value), 'PnL']}
            labelFormatter={(label: number) => {
              const d = data[label - 1]
              if (!d) return `Trade #${label}`
              return `${d.question}\nEntry: $${d.entry.toFixed(3)} → Exit: $${d.exit.toFixed(3)}\nHeld: ${d.held}`
            }}
          />
          <ReferenceLine y={0} stroke="rgba(255,255,255,0.15)" />
          <Bar dataKey="pnl" radius={[3, 3, 0, 0]}>
            {data.map((entry, index) => (
              <Cell key={index} fill={entry.pnl >= 0 ? 'rgba(63,185,80,0.7)' : 'rgba(248,81,73,0.7)'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
