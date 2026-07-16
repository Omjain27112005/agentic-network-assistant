// Alerts Center — real-time alert feed from Zustand (WebSocket)
import { useNetworkStore } from '../store/networkStore';
import { AlertTriangle, Zap, Info, AlertOctagon } from 'lucide-react';

const SEVERITY_CONFIG = {
  EMERGENCY: { icon: AlertOctagon, color: 'var(--severity-emergency)', bg: 'rgba(239,68,68,0.08)', border: 'rgba(239,68,68,0.3)' },
  CRITICAL:  { icon: AlertTriangle, color: 'var(--severity-critical)', bg: 'rgba(249,115,22,0.08)', border: 'rgba(249,115,22,0.3)' },
  WARNING:   { icon: Zap,          color: 'var(--severity-warning)',   bg: 'rgba(245,158,11,0.08)', border: 'rgba(245,158,11,0.3)' },
  INFO:      { icon: Info,         color: 'var(--severity-info)',      bg: 'rgba(59,130,246,0.08)',  border: 'rgba(59,130,246,0.3)' },
};

function AlertRow({ alert }) {
  const cfg = SEVERITY_CONFIG[alert.severity] || SEVERITY_CONFIG.INFO;
  const Icon = cfg.icon;
  const time = alert.timestamp ? new Date(alert.timestamp).toLocaleTimeString() : '—';

  return (
    <div className="animate-slide-right" style={{
      padding: '16px 20px',
      background: cfg.bg,
      border: `1px solid ${cfg.border}`,
      borderRadius: 'var(--radius-md)',
      display: 'flex', alignItems: 'flex-start', gap: 14,
    }}>
      <div style={{ marginTop: 2 }}>
        <Icon size={18} color={cfg.color} />
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
          <span className={`badge badge-${alert.severity?.toLowerCase()}`}>{alert.severity}</span>
          <span style={{ fontWeight: 700, fontSize: 15 }}>{alert.device_id}</span>
          <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{alert.alert_type?.replace(/_/g, ' ')}</span>
          <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-muted)' }}>{time}</span>
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{alert.threshold_breached}</div>
        {alert.status && (
          <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-muted)' }}>
            Status: <span style={{ color: cfg.color }}>{alert.status}</span>
            {alert.jira_ticket_id && (
              <span style={{ marginLeft: 10, color: 'var(--accent-blue)' }}>🎫 {alert.jira_ticket_id}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function Alerts() {
  const { alerts, wsConnected } = useNetworkStore();

  return (
    <div style={{ animation: 'fadeInUp 0.3s ease' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 28 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 800, marginBottom: 4 }}>Alert Center</h1>
          <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
            {wsConnected ? '🟢 Live feed' : '🔴 Disconnected'} · {alerts.length} active alert{alerts.length !== 1 ? 's' : ''}
          </div>
        </div>
      </div>

      {alerts.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '80px 0' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>✅</div>
          <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 8 }}>No Active Alerts</div>
          <div style={{ color: 'var(--text-muted)' }}>All devices are operating normally</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {alerts.map(alert => <AlertRow key={alert.alert_id} alert={alert} />)}
        </div>
      )}
    </div>
  );
}
