import { useState, useEffect } from 'react'
import { api } from '../api'

const SEV = {
  info:     { color: '#00b4d8', bg: '#00b4d810', icon: 'ℹ️' },
  warning:  { color: '#ffd166', bg: '#ffd16610', icon: '⚠️' },
  critical: { color: '#ff4d6d', bg: '#ff4d6d10', icon: '🚨' },
}

export default function Alerts() {
  const [alerts, setAlerts] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all') // all | unresolved | critical

  const load = async () => {
    setLoading(true)
    try {
      const params = {}
      if (filter === 'unresolved') params.unresolved_only = true
      const data = await api.alerts({ ...params, limit: 100 })
      setAlerts(filter === 'critical' ? data.filter(a => a.severity === 'critical') : data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [filter])

  const resolve = async (id) => {
    await api.resolveAlert(id)
    load()
  }

  const unresolved = alerts.filter(a => !a.resolved_at).length

  return (
    <div style={{ padding: '28px 32px', maxWidth: 900, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26, fontWeight: 700 }}>Alerts</h1>
          <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 4 }}>
            {unresolved} unresolved · {alerts.length} total shown
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {['all', 'unresolved', 'critical'].map(f => (
            <button key={f} onClick={() => setFilter(f)} style={{
              padding: '8px 14px', borderRadius: 7, cursor: 'pointer', fontSize: 12,
              background: filter === f ? 'var(--accent)' : 'none',
              border: `1px solid ${filter === f ? 'var(--accent)' : 'var(--border)'}`,
              color: filter === f ? '#000' : 'var(--muted)',
              fontWeight: filter === f ? 700 : 400,
              fontFamily: 'Space Mono',
            }}>{f}</button>
          ))}
        </div>
      </div>

      {loading ? (
        <div style={{ color: 'var(--muted)', textAlign: 'center', padding: 60 }}>Loading…</div>
      ) : alerts.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '60px 0' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>✅</div>
          <div style={{ color: 'var(--muted)' }}>No alerts matching filter</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {alerts.map(a => {
            const s = SEV[a.severity] || SEV.info
            return (
              <div key={a.id} style={{
                background: a.resolved_at ? 'var(--card)' : s.bg,
                border: `1px solid ${a.resolved_at ? 'var(--border)' : s.color + '40'}`,
                borderRadius: 10, padding: '16px 20px',
                display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16,
                opacity: a.resolved_at ? 0.6 : 1,
              }}>
                <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
                  <span style={{ fontSize: 20, flexShrink: 0, marginTop: 2 }}>{s.icon}</span>
                  <div>
                    <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 4 }}>
                      <span style={{ fontFamily: 'Space Mono', fontSize: 11, color: s.color, background: s.bg, padding: '2px 8px', borderRadius: 4, border: `1px solid ${s.color}30` }}>
                        {a.severity.toUpperCase()}
                      </span>
                      <span style={{ fontFamily: 'Space Mono', fontSize: 11, color: 'var(--muted)' }}>
                        {a.type}
                      </span>
                    </div>
                    <div style={{ fontSize: 14, color: 'var(--text)', marginBottom: 6 }}>{a.message}</div>
                    <div style={{ fontSize: 11, color: 'var(--muted)' }}>
                      Camera {a.camera_id}
                      {a.zone_id && ` · Zone ${a.zone_id}`}
                      &nbsp;·&nbsp;
                      {new Date(a.created_at).toLocaleString()}
                      {a.resolved_at && (
                        <span style={{ color: '#00ff9d', marginLeft: 10 }}>
                          ✓ Resolved {new Date(a.resolved_at).toLocaleTimeString()}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                {!a.resolved_at && (
                  <button onClick={() => resolve(a.id)} style={{
                    flexShrink: 0, padding: '7px 14px', background: 'none',
                    border: '1px solid var(--border)', borderRadius: 7,
                    color: 'var(--text)', cursor: 'pointer', fontSize: 12,
                    transition: 'all 0.15s',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = '#00ff9d'; e.currentTarget.style.color = '#00ff9d' }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text)' }}>
                    Mark Resolved
                  </button>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
