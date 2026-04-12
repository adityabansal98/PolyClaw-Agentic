import { ConfirmationModal } from '../components/ConfirmationModal'
import { Panel } from '../components/Panel'
import { StatusPill } from '../components/StatusPill'
import { formatRelativeTime } from '../lib/format'
import type { AlertItem, LogEvent, ServiceHealth } from '../lib/types'

interface OperationsPageProps {
  services: ServiceHealth[]
  logs: LogEvent[]
  alerts: AlertItem[]
  killSwitchEnabled: boolean
  pausedCategories: string[]
  lastRefreshAt: string
  pendingKillSwitchAction: boolean
  onToggleKillSwitch: () => void
  onCancelToggle: () => void
}

export function OperationsPage({
  services,
  logs,
  alerts,
  killSwitchEnabled,
  pausedCategories,
  lastRefreshAt,
  pendingKillSwitchAction,
  onToggleKillSwitch,
  onCancelToggle,
}: OperationsPageProps) {
  return (
    <>
      <div className="page-stack">
        <div className="hero-strip">
          <div>
            <p className="eyebrow">Operations</p>
            <h1>Health, traceability, and execution safety controls</h1>
            <p className="muted">
              This tab is the failsafe layer. It surfaces stale data, logs, service status, and the global kill switch.
            </p>
          </div>
        </div>

        <section className="overview-grid overview-grid--dense">
          <Panel
            title="Execution controls"
            subtitle={`Last refresh ${formatRelativeTime(lastRefreshAt)}`}
            action={
              <button
                className={`button ${killSwitchEnabled ? 'button--danger' : 'button--primary'}`}
                type="button"
                onClick={onToggleKillSwitch}
              >
                {killSwitchEnabled ? 'Disable kill switch' : 'Enable kill switch'}
              </button>
            }
          >
            <div className="split-metrics">
              <article className="metric-card">
                <p className="metric-card__label">Kill switch</p>
                <strong>{killSwitchEnabled ? 'Enabled' : 'Armed but idle'}</strong>
                <span>When enabled, new approvals and promotions are blocked.</span>
              </article>
              <article className="metric-card">
                <p className="metric-card__label">Paused categories</p>
                <strong>{pausedCategories.length}</strong>
                <span>{pausedCategories.length ? pausedCategories.join(', ') : 'No category pauses active'}</span>
              </article>
            </div>
          </Panel>

          <Panel title="Alerting" subtitle="Operational issues surfaced before execution">
            <div className="alert-stack">
              {alerts.map((alert) => (
                <article key={alert.id} className={`alert-card alert-card--${alert.tone}`}>
                  <div>
                    <p className="alert-card__title">{alert.title}</p>
                    <p className="muted">{alert.description}</p>
                  </div>
                </article>
              ))}
            </div>
          </Panel>
        </section>

        <section className="overview-grid overview-grid--dense">
          <Panel title="Service health" subtitle="Critical dependencies that gate approvals and executions">
            <div className="service-card-grid">
              {services.map((service) => (
                <article key={service.id} className="service-card">
                  <div className="service-card__header">
                    <div>
                      <p className="service-card__title">{service.name}</p>
                      <p className="muted">{service.description}</p>
                    </div>
                    <StatusPill
                      tone={
                        service.status === 'healthy'
                          ? 'positive'
                          : service.status === 'degraded'
                            ? 'warning'
                            : 'critical'
                      }
                    >
                      {service.status}
                    </StatusPill>
                  </div>
                  <dl className="service-card__details">
                    <div>
                      <dt>Latency</dt>
                      <dd>{service.latencyMs} ms</dd>
                    </div>
                    <div>
                      <dt>Owner</dt>
                      <dd>{service.owner}</dd>
                    </div>
                    <div>
                      <dt>Heartbeat</dt>
                      <dd>{formatRelativeTime(service.lastHeartbeatAt)}</dd>
                    </div>
                    <div>
                      <dt>Critical</dt>
                      <dd>{service.critical ? 'Yes' : 'No'}</dd>
                    </div>
                  </dl>
                </article>
              ))}
            </div>
          </Panel>

          <Panel title="Audit log" subtitle="Recent approvals, routing changes, and warnings">
            <div className="log-stack">
              {logs.map((log) => (
                <article key={log.id} className={`log-row log-row--${log.level}`}>
                  <div className="log-row__meta">
                    <StatusPill
                      tone={
                        log.level === 'info' ? 'info' : log.level === 'warning' ? 'warning' : 'critical'
                      }
                    >
                      {log.level}
                    </StatusPill>
                    <span>{formatRelativeTime(log.timestamp)}</span>
                  </div>
                  <p className="list-row__title">{log.message}</p>
                  <p className="muted">
                    {log.source}
                    {log.user ? ` · ${log.user}` : ''}
                  </p>
                </article>
              ))}
            </div>
          </Panel>
        </section>
      </div>

      <ConfirmationModal
        open={pendingKillSwitchAction}
        title={killSwitchEnabled ? 'Disable the global kill switch?' : 'Enable the global kill switch?'}
        description={
          killSwitchEnabled
            ? 'Disabling the kill switch will allow new live approvals and paper promotions again.'
            : 'Enabling the kill switch will stop new approvals while keeping the dashboard visible for monitoring.'
        }
        confirmLabel={killSwitchEnabled ? 'Disable kill switch' : 'Enable kill switch'}
        confirmTone={killSwitchEnabled ? 'primary' : 'danger'}
        onCancel={onCancelToggle}
        onConfirm={onToggleKillSwitch}
      />
    </>
  )
}
