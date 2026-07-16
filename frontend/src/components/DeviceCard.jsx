// Device card — shows one device's live status and metrics
import { useNavigate } from 'react-router-dom';
import { Router, Network, Wifi } from 'lucide-react';

const TYPE_ICON = { ROUTER: Router, SWITCH: Network, ACCESS_POINT: Wifi };
const TYPE_COLOR = {
  ROUTER:       'var(--accent-blue)',
  SWITCH:       'var(--accent-purple)',
  ACCESS_POINT: 'var(--accent-cyan)',
};

function StatusBadge({ status }) {
  const cls = `badge badge-${(status || 'unknown').toLowerCase()}`;
  return <span className={cls}>{status || 'UNKNOWN'}</span>;
}

function MetricBar({ value, max = 100, color }) {
  const pct = Math.min((value / max) * 100, 100);
  const barColor =
    pct > 90 ? 'var(--accent-red)' :
    pct > 70 ? 'var(--accent-yellow)' :
    color || 'var(--accent-blue)';
  return (
    <div style={{ height: 3, background: 'var(--border)', borderRadius: 2, overflow: 'hidden' }}>
      <div style={{ width: `${pct}%`, height: '100%', background: barColor, borderRadius: 2, transition: 'width 0.5s ease' }} />
    </div>
  );
}

export default function DeviceCard({ device }) {
  const navigate = useNavigate();
  const Icon = TYPE_ICON[device.device_type] || Network;
  const iconColor = TYPE_COLOR[device.device_type] || 'var(--accent-blue)';
  const isDown = device.status === 'DOWN';
  const isDegraded = device.status === 'DEGRADED';

  return (
    <div
      className="card"
      onClick={() => navigate(`/devices/${device.device_id}`)}
      style={{
        padding: 20,
        cursor: 'pointer',
        border: isDown ? '1px solid rgba(239,68,68,0.35)' : isDegraded ? '1px solid rgba(245,158,11,0.35)' : undefined,
        animation: 'fadeInUp 0.3s ease',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 8,
            background: `${iconColor}20`,
            border: `1px solid ${iconColor}40`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Icon size={18} color={iconColor} />
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 16 }}>{device.device_id}</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{device.device_type}</div>
          </div>
        </div>
        <StatusBadge status={device.status} />
      </div>

      {/* Location */}
      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 14 }}>
        📍 {device.location}
      </div>

      {/* Key Metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
        {[
          { label: 'Latency', value: device.latency_ms != null ? `${device.latency_ms}ms` : '—', warn: device.latency_ms > 100 },
          { label: 'Packet Loss', value: device.packet_loss_percent != null ? `${device.packet_loss_percent}%` : '—', warn: device.packet_loss_percent > 1 },
        ].map(({ label, value, warn }) => (
          <div key={label}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>{label}</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: warn ? 'var(--accent-yellow)' : 'var(--text-primary)' }}>{value}</div>
          </div>
        ))}
      </div>

      {/* CPU & Memory bars */}
      {device.cpu_percent != null && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>
              <span>CPU</span><span>{device.cpu_percent}%</span>
            </div>
            <MetricBar value={device.cpu_percent} color="var(--accent-blue)" />
          </div>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-muted)', marginBottom: 3 }}>
              <span>Memory</span><span>{device.memory_percent}%</span>
            </div>
            <MetricBar value={device.memory_percent} color="var(--accent-purple)" />
          </div>
        </div>
      )}

      {isDown && (
        <div style={{ marginTop: 12, padding: '8px 12px', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 8, fontSize: 12, color: 'var(--accent-red)', fontWeight: 500 }}>
          ⚠️ Device unreachable
        </div>
      )}
    </div>
  );
}
