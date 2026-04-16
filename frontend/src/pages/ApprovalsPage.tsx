// Phase 7 — Human approval dashboard for live trading promotion.
//
// Lists pending and resolved approval requests. Humans review agent track records
// and either approve (with signed confirmation + USDC limit) or reject.
import { useEffect, useState } from 'react'

type ApprovalRequest = {
  id: number
  agent_id: string
  status: 'pending' | 'approved' | 'rejected' | 'revoked'
  requested_at_ms: number
  requested_by: string
  message: string
  reviewed_at_ms: number | null
  confirmation_text: string | null
  max_live_usdc: number | null
}

function fmtDate(ms: number | null) {
  if (!ms) return '\u2014'
  return new Date(ms).toLocaleString()
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    pending: '#f59e0b',
    approved: '#10b981',
    rejected: '#ef4444',
    revoked: '#6b7280',
  }
  return (
    <span
      style={{
        background: colors[status] || '#888',
        color: '#fff',
        padding: '2px 8px',
        borderRadius: 4,
        fontSize: 12,
        fontWeight: 600,
      }}
    >
      {status.toUpperCase()}
    </span>
  )
}

export function ApprovalsPage() {
  const [requests, setRequests] = useState<ApprovalRequest[]>([])
  const [loading, setLoading] = useState(true)

  function refresh() {
    fetch('/api/v1/approvals')
      .then(r => r.json())
      .then(data => setRequests(data.items || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { refresh() }, [])

  const pending = requests.filter(r => r.status === 'pending')
  const resolved = requests.filter(r => r.status !== 'pending')

  return (
    <div className="approvals-page">
      <h1>Live Trading Approvals</h1>
      <p className="muted">
        Review agent track records before approving them for real-money trading.
        Every approval requires a signed confirmation and a USDC spending cap.
      </p>

      <h2>Pending Requests ({pending.length})</h2>
      {loading ? <p className="muted">Loading...</p> : null}
      {!loading && pending.length === 0 ? (
        <p className="muted">No pending requests. Agents request promotion via POST /api/v1/agents/:id/request-live.</p>
      ) : null}

      {pending.map(r => (
        <div key={r.id} className="approval-card approval-card--pending">
          <div className="approval-card__header">
            <strong>{r.agent_id}</strong>
            <StatusBadge status={r.status} />
          </div>
          <p className="muted">Requested {fmtDate(r.requested_at_ms)} by {r.requested_by}</p>
          {r.message && <p className="approval-card__message">"{r.message}"</p>}
          <p className="muted">
            To approve: POST /api/v1/agents/{r.agent_id}/approve-live with confirmation_text + max_live_usdc.
            To reject: use the kill switch DELETE /api/v1/agents/{r.agent_id}/live.
          </p>
        </div>
      ))}

      <h2>History ({resolved.length})</h2>
      <table className="arena-leaderboard">
        <thead>
          <tr>
            <th>Agent</th>
            <th>Status</th>
            <th>Requested</th>
            <th>Reviewed</th>
            <th>Limit</th>
            <th>Confirmation</th>
          </tr>
        </thead>
        <tbody>
          {resolved.map(r => (
            <tr key={r.id}>
              <td>{r.agent_id}</td>
              <td><StatusBadge status={r.status} /></td>
              <td className="muted">{fmtDate(r.requested_at_ms)}</td>
              <td className="muted">{fmtDate(r.reviewed_at_ms)}</td>
              <td>{r.max_live_usdc ? `$${r.max_live_usdc.toLocaleString()}` : '\u2014'}</td>
              <td className="muted" style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {r.confirmation_text || '\u2014'}
              </td>
            </tr>
          ))}
          {resolved.length === 0 && !loading && (
            <tr><td colSpan={6} className="muted">No resolved requests yet.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
