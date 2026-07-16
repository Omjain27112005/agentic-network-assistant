// Sidebar navigation component
import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Bell, FileText, MessageSquare, Activity, Wifi, WifiOff } from 'lucide-react';
import { useNetworkStore } from '../store/networkStore';

const NAV_ITEMS = [
  { to: '/',          icon: LayoutDashboard, label: 'Dashboard'    },
  { to: '/alerts',    icon: Bell,            label: 'Alerts'       },
  { to: '/incidents', icon: FileText,        label: 'Incidents'    },
  { to: '/chat',      icon: MessageSquare,   label: 'AI Chat'      },
];

export default function Sidebar() {
  const { healthScore, wsConnected, alertCount } = useNetworkStore();

  const healthColor =
    healthScore >= 90 ? 'var(--accent-green)' :
    healthScore >= 70 ? 'var(--accent-yellow)' :
                        'var(--accent-red)';

  return (
    <aside className="sidebar">
      {/* Logo */}
      <div style={{ padding: '24px 20px 16px', borderBottom: '1px solid var(--border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 10,
            background: 'linear-gradient(135deg, var(--accent-blue), var(--accent-purple))',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Activity size={18} color="white" />
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 14, lineHeight: 1.2 }}>NetAgent</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>AI-Powered Monitor</div>
          </div>
        </div>
      </div>

      {/* Health Score */}
      <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          Network Health
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ fontSize: 32, fontWeight: 800, color: healthColor, lineHeight: 1 }}>
            {Math.round(healthScore)}
          </div>
          <div style={{ fontSize: 16, color: 'var(--text-muted)' }}>/100</div>
        </div>
        <div style={{ marginTop: 8, height: 4, background: 'var(--border)', borderRadius: 2 }}>
          <div style={{
            height: '100%', borderRadius: 2,
            width: `${healthScore}%`,
            background: healthColor,
            transition: 'width 0.5s ease',
          }} />
        </div>
      </div>

      {/* Nav */}
      <nav style={{ flex: 1, padding: '12px 12px' }}>
        {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '10px 12px',
              borderRadius: 'var(--radius-md)',
              marginBottom: 2,
              fontSize: 14,
              fontWeight: 500,
              color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
              background: isActive ? 'rgba(59,130,246,0.12)' : 'transparent',
              border: isActive ? '1px solid rgba(59,130,246,0.25)' : '1px solid transparent',
              transition: 'all 0.15s ease',
              textDecoration: 'none',
              position: 'relative',
            })}
          >
            <Icon size={16} />
            {label}
            {label === 'Alerts' && alertCount > 0 && (
              <span style={{
                marginLeft: 'auto',
                background: 'var(--accent-red)',
                color: 'white',
                fontSize: 10,
                fontWeight: 700,
                padding: '1px 6px',
                borderRadius: 999,
                minWidth: 18,
                textAlign: 'center',
              }}>
                {alertCount}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* WS Status */}
      <div style={{
        padding: '16px 20px',
        borderTop: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        {wsConnected
          ? <><span className="pulse-dot" /><span style={{ fontSize: 12, color: 'var(--accent-green)' }}>Live</span></>
          : <><WifiOff size={14} color="var(--accent-red)" /><span style={{ fontSize: 12, color: 'var(--accent-red)' }}>Disconnected</span></>
        }
      </div>
    </aside>
  );
}
