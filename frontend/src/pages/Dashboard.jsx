// Dashboard — main landing page with live device grid + health overview
import { useNetworkStore } from '../store/networkStore';
import DeviceCard from '../components/DeviceCard';
import { Activity, AlertTriangle, Server, TrendingUp } from 'lucide-react';

function StatCard({ icon: Icon, label, value, color, sub }) {
  return (
    <div className="card" style={{ padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <span style={{ fontSize: 13, color: 'var(--text-secondary)', fontWeight: 500 }}>{label}</span>
        <div style={{ width: 32, height: 32, borderRadius: 8, background: `${color}20`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Icon size={16} color={color} />
        </div>
      </div>
      <div style={{ fontSize: 32, fontWeight: 800, color, lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

export default function Dashboard() {
  const { devices, alerts, healthScore, lastUpdated, wsConnected } = useNetworkStore();

  const upCount       = devices.filter(d => d.status === 'UP').length;
  const downCount     = devices.filter(d => d.status === 'DOWN').length;
  const degradedCount = devices.filter(d => d.status === 'DEGRADED').length;
  const criticalAlerts = alerts.filter(a => a.severity === 'CRITICAL' || a.severity === 'EMERGENCY').length;

  const healthColor = healthScore >= 90 ? 'var(--accent-green)' : healthScore >= 70 ? 'var(--accent-yellow)' : 'var(--accent-red)';

  return (
    <div style={{ animation: 'fadeInUp 0.3s ease' }}>
      {/* Page Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 28 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 800, marginBottom: 4 }}>Network Dashboard</h1>
          <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
            {wsConnected
              ? <>🟢 Live — Last updated {lastUpdated ? lastUpdated.toLocaleTimeString() : '—'}</>
              : '🔴 WebSocket disconnected — data may be stale'}
          </div>
        </div>
      </div>

      {/* Emergency Banner */}
      {downCount > 0 && (
        <div className="animate-shake" style={{
          marginBottom: 20, padding: '12px 20px',
          background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.4)',
          borderRadius: 'var(--radius-md)', display: 'flex', alignItems: 'center', gap: 10,
        }}>
          <AlertTriangle size={18} color="var(--accent-red)" />
          <span style={{ fontWeight: 600, color: 'var(--accent-red)' }}>
            ⚠️ {downCount} device{downCount > 1 ? 's are' : ' is'} DOWN — immediate action required
          </span>
        </div>
      )}

      {/* Stat Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 28 }}>
        <StatCard icon={Activity}      label="Health Score"     value={`${Math.round(healthScore)}`} color={healthColor}               sub="out of 100" />
        <StatCard icon={Server}        label="Devices Up"       value={upCount}                        color="var(--accent-green)"       sub={`of ${devices.length} total`} />
        <StatCard icon={TrendingUp}    label="Degraded"         value={degradedCount}                  color="var(--accent-yellow)"      sub="need attention" />
        <StatCard icon={AlertTriangle} label="Critical Alerts"  value={criticalAlerts}                 color="var(--accent-red)"         sub="active now" />
      </div>

      {/* Device Grid */}
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16 }}>
          Device Status <span style={{ fontSize: 13, color: 'var(--text-muted)', fontWeight: 400 }}>({devices.length} devices)</span>
        </h2>
        {devices.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-muted)' }}>
            <div className="skeleton" style={{ height: 200, borderRadius: 16 }} />
            <p style={{ marginTop: 16 }}>Waiting for live data...</p>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16 }}>
            {devices.map(d => <DeviceCard key={d.device_id} device={d} />)}
          </div>
        )}
      </div>
    </div>
  );
}
