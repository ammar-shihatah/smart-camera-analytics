import { useState, useEffect, useRef, useCallback } from 'react'
import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import StatCard from '../components/StatCard'
import { api, createDashboardWS } from '../api'

const ZONE_COLORS = {
  entrance:    '#00b4d8',
  counter:     '#f72585',
  waiting:     '#ffd166',
  shared_area: '#8ecae6',
  room_area:   '#a8dadc',
}

const SEV_COLORS = { info: '#00b4d8', warning: '#ffd166', critical: '#ff4d6d' }

function fmt(secs) {
  if (!secs) return '0s'
  if (secs < 60) return `${Math.round(secs)}s`
  return `${Math.floor(secs / 60)}m ${Math.round(secs % 60)}s`
}

export default function Dashboard() {
  const [overview, setOverview] = useState(null)
  const [alerts, setAlerts] = useState([])
  const [history, setHistory] = useState([]) // live people count over time
  const [wsStatus, setWsStatus] = useState('connecting')
  const [liveUpdate, setLiveUpdate] = useState(null)
  const wsRef = useRef(null)
  const histRef = useRef([])

  const loadData = useCallback(async () => {
    try {
      const [ov, al] = await Promise.all([api.overview(), api.alerts({ unresolved_only: true, limit: 10 })])
      setOverview(ov)
      setAlerts(al)
    } catch (e) {
      console.error('Dashboard load failed:', e)
    }
  }, [])

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 15000)
    return () => clearInterval(interval)
  }, [loadData])

  useEffect(() => {
    const ws = createDashboardWS((msg) => {
      if (msg.type === 'live_update') {
        setWsStatus('live')
        setLiveUpdate(msg)
        const now = new Date().toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
        histRef.current = [...histRef.current.slice(-29), { time: now, count: msg.people_count }]
        setHistory([...histRef.current])
      } else if (msg.type === 'alert') {
        setAlerts(prev => [msg.data, ...prev].slice(0, 10))
      } else if (msg.type === 'pong') {
        setWsStatus('live')
      }
    })
    ws.onopen = () => setWsStatus('live')
    ws.onclose = () => setWsStatus('disconnected')
    ws.onerror = () => setWsStatus('error')
    wsRef.current = ws
    return () => ws.close()
  }, [])

  const resolveAlert = async (id) => {
    try {
      await api.resolveAlert(id)
      setAlerts(prev => prev.filter(a => a.id !== id))
    } catch {}
  }

  const peopleNow = liveUpdate?.people_count ?? overview?.total_people_now ?? 0
  const zoneCounts = liveUpdate?.zone_counts ?? {}

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1400, margin: '0 auto' }}>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 32 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26, fontWeight: 700, letterSpacing: -0.5 }}>Analytics Overview</h1>
          <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 4 }}>
            Real-time behavior insights · Privacy-first · No identity tracking
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            width: 8, height: 8, borderRadius: '50%',
            background: wsStatus === 'live' ? '#00ff9d' : wsStatus === 'connecting' ? '#ffd166' : '#ff4d6d',
            display: 'inline-block',
            boxShadow: wsStatus === 'live' ? '0 0 8px #00ff9d' : 'none',
            animation: wsStatus === 'live' ? 'pulse 2s infinite' : 'none',
          }} />
          <span style={{ fontSize: 12, color: 'var(--muted)', fontFamily: 'Space Mono' }}>
            {wsStatus === 'live' ? 'LIVE' : wsStatus.toUpperCase()}
          </span>
        </div>
      </div>

      {/* Top Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 16, marginBottom: 28 }}>
        <StatCard label="People Now" value={peopleNow} icon="👥" color="#00ff9d" />
        <StatCard label="Today's Visits" value={overview?.total_visits_today} icon="📈" color="#00b4d8" />
        <StatCard label="Avg. Dwell Time" value={fmt(overview?.avg_dwell_seconds)} icon="⏱" color="#ffd166" />
        <StatCard label="Active Alerts" value={overview?.active_alerts} icon="🔔" color="#ff4d6d" />
        <StatCard label="Cameras Online" value={`${overview?.cameras_online ?? 0}/${overview?.cameras_total ?? 0}`} icon="📷" color="#a8dadc" />
      </div>

      {/* Live Chart + Alerts */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: 20, marginBottom: 24 }}>

        {/* People count over time */}
        <div style={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 12, padding: '20px 24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <span style={{ fontWeight: 600, fontSize: 15 }}>Live People Count</span>
            <span style={{ fontSize: 11, color: 'var(--muted)', fontFamily: 'Space Mono' }}>LAST 30 READINGS</span>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={history} margin={{ left: -20 }}>
              <defs>
                <linearGradient id="cg" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#00ff9d" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#00ff9d" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="time" tick={{ fill: 'var(--muted)', fontSize: 10 }} interval="preserveStartEnd" />
              <YAxis tick={{ fill: 'var(--muted)', fontSize: 10 }} allowDecimals={false} />
              <Tooltip contentStyle={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 8 }} />
              <Area type="monotone" dataKey="count" stroke="#00ff9d" fill="url(#cg)" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Alerts panel */}
        <div style={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 12, padding: '20px 24px', overflow: 'hidden' }}>
          <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 14, display: 'flex', justifyContent: 'space-between' }}>
            <span>Active Alerts</span>
            <span style={{ fontSize: 12, color: 'var(--muted)' }}>{alerts.length} unresolved</span>
          </div>
          <div style={{ maxHeight: 220, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {alerts.length === 0 ? (
              <div style={{ color: 'var(--muted)', fontSize: 13, textAlign: 'center', padding: '24px 0' }}>
                ✅ No active alerts
              </div>
            ) : alerts.map(a => (
              <div key={a.id} style={{
                background: `${SEV_COLORS[a.severity] || '#888'}10`,
                border: `1px solid ${SEV_COLORS[a.severity] || '#888'}30`,
                borderRadius: 8, padding: '10px 12px',
                display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8,
              }}>
                <div>
                  <div style={{ fontSize: 11, color: SEV_COLORS[a.severity], fontFamily: 'Space Mono', marginBottom: 3 }}>
                    {a.severity?.toUpperCase()} · {a.type}
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--text)' }}>{a.message}</div>
                  <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 3 }}>
                    Cam {a.camera_id} · {new Date(a.created_at).toLocaleTimeString()}
                  </div>
                </div>
                <button onClick={() => resolveAlert(a.id)} style={{
                  background: 'none', border: '1px solid var(--border)', borderRadius: 6,
                  color: 'var(--muted)', cursor: 'pointer', padding: '4px 8px', fontSize: 11,
                  flexShrink: 0,
                }}>✓</button>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Zone Analytics */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>

        {/* Zone bar chart */}
        <div style={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 12, padding: '20px 24px' }}>
          <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 16 }}>Zone Activity (Current)</div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={overview?.zone_analytics || []} margin={{ left: -20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="zone_name" tick={{ fill: 'var(--muted)', fontSize: 10 }} />
              <YAxis tick={{ fill: 'var(--muted)', fontSize: 10 }} allowDecimals={false} />
              <Tooltip contentStyle={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 8 }} />
              <Bar dataKey="current_count" radius={[4, 4, 0, 0]}>
                {(overview?.zone_analytics || []).map((z, i) => (
                  <Cell key={i} fill={ZONE_COLORS[z.zone_type] || '#888'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Zone cards */}
        <div style={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 12, padding: '20px 24px' }}>
          <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 14 }}>Zone Details</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxHeight: 220, overflowY: 'auto' }}>
            {(overview?.zone_analytics || []).map(z => (
              <div key={z.zone_id} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '10px 14px',
                background: `${ZONE_COLORS[z.zone_type] || '#888'}10`,
                border: `1px solid ${ZONE_COLORS[z.zone_type] || '#888'}25`,
                borderRadius: 8,
              }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>{z.zone_name}</div>
                  <div style={{ fontSize: 11, color: 'var(--muted)' }}>
                    {z.zone_type} · {z.total_visits_today} visits today
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 20, fontWeight: 700, fontFamily: 'Space Mono', color: ZONE_COLORS[z.zone_type] || '#888' }}>
                    {z.current_count}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--muted)' }}>avg {fmt(z.avg_dwell_seconds)}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
