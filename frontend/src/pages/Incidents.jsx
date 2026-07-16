// Incidents — historical incidents from PostgreSQL via REST API
import { useEffect } from 'react';
import axios from 'axios';
import { useNetworkStore } from '../store/networkStore';
import { ExternalLink, CheckCircle, Clock } from 'lucide-react';

const API = 'http://localhost:8000/api/v1';

export default function Incidents() {
  const { incidents, setIncidents } = useNetworkStore();

  useEffect(() => {
    axios.get(`${API}/incidents`)
      .then(r => setIncidents(r.data))
      .catch(e => console.error('Failed to fetch incidents:', e));
  }, []);

  return (
    <div style={{ animation: 'fadeInUp 0.3s ease' }}>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, marginBottom: 4 }}>Incident History</h1>
        <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
          AI-diagnosed incidents · stored permanently in PostgreSQL · {incidents.length} records
        </div>
      </div>

      {incidents.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '80px 0', color: 'var(--text-muted)' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>📋</div>
          <div>No incidents recorded yet. Waiting for the AI Agent to diagnose alerts.</div>
        </div>
      ) : (
        <div className="card" style={{ overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)', background: 'var(--bg-surface)' }}>
                {['Device', 'Type', 'Severity', 'Root Cause', 'Confidence', 'Jira Ticket', 'Status', 'Created'].map(h => (
                  <th key={h} style={{ padding: '12px 16px', textAlign: 'left', fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {incidents.map((inc, i) => (
                <tr key={inc.id} style={{
                  borderBottom: '1px solid var(--border)',
                  background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)',
                  transition: 'background 0.15s',
                }}>
                  <td style={{ padding: '14px 16px', fontWeight: 700 }}>{inc.device_id}</td>
                  <td style={{ padding: '14px 16px', fontSize: 13, color: 'var(--text-secondary)' }}>{inc.alert_type?.replace(/_/g, ' ')}</td>
                  <td style={{ padding: '14px 16px' }}>
                    <span className={`badge badge-${inc.severity?.toLowerCase()}`}>{inc.severity}</span>
                  </td>
                  <td style={{ padding: '14px 16px', fontSize: 13, maxWidth: 280 }}>
                    <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-secondary)' }}>
                      {inc.root_cause || '—'}
                    </div>
                  </td>
                  <td style={{ padding: '14px 16px', fontWeight: 600 }}>
                    {inc.confidence_score != null ? `${Math.round(inc.confidence_score * 100)}%` : '—'}
                  </td>
                  <td style={{ padding: '14px 16px' }}>
                    {inc.jira_ticket_id
                      ? <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'var(--accent-blue)', fontSize: 13, fontWeight: 500 }}>
                          <ExternalLink size={12} /> {inc.jira_ticket_id}
                        </span>
                      : <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>—</span>}
                  </td>
                  <td style={{ padding: '14px 16px' }}>
                    {inc.resolved
                      ? <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'var(--accent-green)', fontSize: 12 }}><CheckCircle size={12} /> Resolved</span>
                      : <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'var(--accent-yellow)', fontSize: 12 }}><Clock size={12} /> Open</span>}
                  </td>
                  <td style={{ padding: '14px 16px', fontSize: 12, color: 'var(--text-muted)' }}>
                    {inc.created_at ? new Date(inc.created_at).toLocaleString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
