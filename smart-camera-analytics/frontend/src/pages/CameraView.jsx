import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { api, createCameraWS } from '../api'
import StatCard from '../components/StatCard'

const EXPR_LABELS = {
  apparent_smile: { label: '😊 Apparent Smile', color: '#00ff9d' },
  neutral:        { label: '😐 Neutral',         color: '#ffd166' },
  face_not_visible: { label: '🚫 Not Visible',   color: '#888' },
}

export default function CameraView() {
  const { id } = useParams()
  const camId = parseInt(id)
  const [camera, setCamera] = useState(null)
  const [zones, setZones] = useState([])
  const [analytics, setAnalytics] = useState(null)
  const [liveData, setLiveData] = useState(null)
  const [wsStatus, setWsStatus] = useState('connecting')
  const [showAddZone, setShowAddZone] = useState(false)
  const [zoneForm, setZoneForm] = useState({ name: '', type: 'counter', polygon_json: '[[100,100],[500,100],[500,400],[100,400]]' })
  const [streamStatus, setStreamStatus] = useState('loading')
  const [streamKey, setStreamKey] = useState(0)
  const [streamProfile, setStreamProfile] = useState('stored')
  const [streamTransport, setStreamTransport] = useState('tcp')
  const [testResult, setTestResult] = useState(null)
  const [testing, setTesting] = useState(false)
  const wsRef = useRef(null)

  const streamUrl = api.streamUrl(camId, {
    fps: streamProfile === 'main' ? 12 : 20,
    profile: streamProfile,
    quality: streamProfile === 'main' ? 3 : 5,
    transport: streamTransport,
  })

  const testConnection = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const res = await api.testCameraConnection(camId)
      setTestResult(res)
      if (res.success) { setStreamKey(k => k + 1); setStreamStatus('loading') }
    } catch (e) {
      setTestResult({ success: false, error_message: e.message })
    } finally {
      setTesting(false)
    }
  }

  useEffect(() => {
    api.camera(camId).then(setCamera).catch(console.error)
    api.zones(camId).then(setZones).catch(console.error)
    api.cameraAnalytics(camId).then(setAnalytics).catch(console.error)
  }, [camId])

  useEffect(() => {
    const ws = createCameraWS(camId, (msg) => {
      if (msg.type === 'live_update') {
        setWsStatus('live')
        setLiveData(msg)
      }
    })
    ws.onopen = () => setWsStatus('live')
    ws.onclose = () => setWsStatus('disconnected')
    wsRef.current = ws
    return () => ws.close()
  }, [camId])

  const addZone = async () => {
    try {
      await api.createZone({
        camera_id: camId,
        name: zoneForm.name,
        type: zoneForm.type,
        polygon_json: JSON.parse(zoneForm.polygon_json),
      })
      setShowAddZone(false)
      const z = await api.zones(camId)
      setZones(z)
    } catch (e) {
      alert('Failed to create zone: ' + e.message)
    }
  }

  const persons = liveData?.tracked_persons || []
  const exprCounts = persons.reduce((acc, p) => {
    acc[p.apparent_expression] = (acc[p.apparent_expression] || 0) + 1
    return acc
  }, {})

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1400, margin: '0 auto' }}>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700 }}>
            {camera?.name || `Camera ${camId}`}
          </h1>
          <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 4 }}>
            {camera?.stream_url || 'No stream configured'} &nbsp;·&nbsp;
            <span style={{
              color: wsStatus === 'live' ? '#00ff9d' : '#888',
              fontFamily: 'Space Mono', fontSize: 11
            }}>● {wsStatus.toUpperCase()}</span>
          </div>
        </div>
        <button onClick={() => setShowAddZone(true)} style={{
          background: 'none', border: '1px solid var(--border)', color: 'var(--text)',
          borderRadius: 8, padding: '9px 16px', cursor: 'pointer', fontSize: 13,
        }}>+ Add Zone</button>
      </div>

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 14, marginBottom: 24 }}>
        <StatCard label="People Now" value={liveData?.people_count ?? 0} icon="👥" color="#00ff9d" small />
        <StatCard label="Today Detections" value={analytics?.total_detections ?? '—'} icon="📊" color="#00b4d8" small />
        <StatCard label="Unique Persons" value={analytics?.unique_persons ?? '—'} icon="🔢" color="#ffd166" small />
        <StatCard label="Avg Dwell" value={analytics?.avg_dwell_seconds ? `${Math.round(analytics.avg_dwell_seconds)}s` : '—'} icon="⏱" color="#a8dadc" small />
      </div>

      {/* ── Live Video Stream ── */}
      <div style={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 12, marginBottom: 20, overflow: 'hidden' }}>
        <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontWeight: 600, fontSize: 15 }}>Live Video</span>
            {streamStatus === 'live' && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: '#ff3333', fontFamily: 'Space Mono' }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#ff3333', boxShadow: '0 0 6px #ff3333', display: 'inline-block' }} />
                LIVE
              </span>
            )}
            {streamStatus === 'loading' && <span style={{ fontSize: 11, color: '#ffd166', fontFamily: 'Space Mono' }}>● CONNECTING</span>}
            {streamStatus === 'error'   && <span style={{ fontSize: 11, color: '#ff4d6d', fontFamily: 'Space Mono' }}>● NO SIGNAL</span>}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <select
              value={streamProfile}
              onChange={e => {
                setStreamProfile(e.target.value)
                setStreamStatus('loading')
                setStreamKey(k => k + 1)
              }}
              style={{
                padding: '5px 10px',
                background: 'var(--bg)',
                border: '1px solid var(--border)',
                borderRadius: 7,
                color: 'var(--text)',
                fontSize: 12,
              }}
            >
              <option value="stored">Saved URL</option>
              <option value="sub">Stable / Sub</option>
              <option value="main">High / Main</option>
            </select>
            <select
              value={streamTransport}
              onChange={e => {
                setStreamTransport(e.target.value)
                setStreamStatus('loading')
                setStreamKey(k => k + 1)
              }}
              style={{
                padding: '5px 10px',
                background: 'var(--bg)',
                border: '1px solid var(--border)',
                borderRadius: 7,
                color: 'var(--text)',
                fontSize: 12,
              }}
            >
              <option value="tcp">TCP</option>
              <option value="udp">UDP</option>
            </select>
            <button onClick={() => { setStreamKey(k => k+1); setStreamStatus('loading') }} style={{ padding: '5px 12px', background: 'none', border: '1px solid var(--border)', borderRadius: 7, color: 'var(--muted)', cursor: 'pointer', fontSize: 12 }}>
              ↺ Reload
            </button>
            <button onClick={testConnection} disabled={testing} style={{ padding: '5px 12px', background: testing ? 'none' : '#00ff9d15', border: '1px solid #00ff9d40', borderRadius: 7, color: '#00ff9d', cursor: 'pointer', fontSize: 12 }}>
              {testing ? 'Testing…' : '⚡ Test Connection'}
            </button>
          </div>
        </div>

        <div style={{ position: 'relative', background: '#0a0a0a', height: 400 }}>
          <img
            key={streamKey}
            src={streamUrl}
            onLoad={() => setStreamStatus('live')}
            onError={() => setStreamStatus('error')}
            alt="Live stream"
            style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
          />
          {streamStatus === 'loading' && (
            <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: '#0a0a0a' }}>
              <style>{`@keyframes spin { to { transform:rotate(360deg) } }`}</style>
              <div style={{ width: 36, height: 36, border: '3px solid #00ff9d30', borderTop: '3px solid #00ff9d', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
              <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 14 }}>Connecting to RTSP stream…</div>
            </div>
          )}
          {streamStatus === 'error' && (
            <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: '#0a0a0a', gap: 10 }}>
              <span style={{ fontSize: 40 }}>📷</span>
              <div style={{ color: '#ff4d6d', fontSize: 13, fontFamily: 'Space Mono' }}>STREAM UNAVAILABLE</div>
              <div style={{ color: 'var(--muted)', fontSize: 12 }}>Click "Test Connection" to diagnose</div>
            </div>
          )}
        </div>

        {testResult && (
          <div style={{ margin: '12px 20px', background: testResult.success ? '#00ff9d10' : '#ff4d6d10', border: `1px solid ${testResult.success ? '#00ff9d30' : '#ff4d6d30'}`, borderRadius: 8, padding: '10px 14px', fontSize: 12 }}>
            <div style={{ color: testResult.success ? '#00ff9d' : '#ff4d6d', fontWeight: 600, marginBottom: 4 }}>
              {testResult.success ? '✓ Connection successful' : '✗ Connection failed'}
              {testResult.connection_time_ms && ` — ${testResult.connection_time_ms}ms`}
              {testResult.resolution && ` — ${testResult.resolution}`}
            </div>
            {testResult.error_message && <div style={{ color: 'var(--muted)', marginBottom: 4 }}>{testResult.error_message}</div>}
            {testResult.suggested_fix && <div style={{ color: '#ffd166' }}>💡 {testResult.suggested_fix}</div>}
          </div>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 20 }}>

        {/* Live tracking view */}
        <div style={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 12, padding: '20px 24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
            <span style={{ fontWeight: 600, fontSize: 15 }}>Live Tracking Feed</span>
            <span style={{ fontSize: 11, color: 'var(--muted)', fontFamily: 'Space Mono' }}>
              {persons.length} tracked
            </span>
          </div>

          {/* Privacy notice */}
          <div style={{
            background: '#00b4d810', border: '1px solid #00b4d830',
            borderRadius: 8, padding: '8px 14px', marginBottom: 14, fontSize: 12, color: '#00b4d8'
          }}>
            🔒 Privacy mode: Temporary IDs only · No identity stored · Metadata only
          </div>

          {/* Person list */}
          <div style={{ maxHeight: 360, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {persons.length === 0 ? (
              <div style={{ color: 'var(--muted)', textAlign: 'center', padding: '40px 0', fontSize: 13 }}>
                {wsStatus === 'live' ? 'No persons detected in frame' : 'Waiting for live data…'}
              </div>
            ) : persons.map(p => (
              <div key={p.tracking_id} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                background: 'var(--bg)', borderRadius: 8, padding: '10px 14px',
                border: p.is_new ? '1px solid #00ff9d40' : '1px solid transparent',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <span style={{
                    fontFamily: 'Space Mono', fontSize: 13, color: 'var(--accent)',
                    background: '#00ff9d15', borderRadius: 6, padding: '3px 8px'
                  }}>{p.tracking_id}</span>
                  <div>
                    <div style={{ fontSize: 12, color: 'var(--text)' }}>
                      {p.zone_name || 'No zone'} &nbsp;
                      {p.zone_entry && <span style={{ fontSize: 10, color: '#00ff9d', marginLeft: 4 }}>↓ entered</span>}
                      {p.zone_exit && <span style={{ fontSize: 10, color: '#ff4d6d', marginLeft: 4 }}>↑ exited</span>}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--muted)' }}>
                      {Math.round(p.dwell_seconds ?? 0)}s dwell · move {((p.movement_score ?? 0) * 100).toFixed(1)}%
                    </div>
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 11, color: EXPR_LABELS[p.apparent_expression]?.color || '#888' }}>
                    {EXPR_LABELS[p.apparent_expression]?.label || p.apparent_expression}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Zones + Expression summary */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Zones */}
          <div style={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 12, padding: '18px 20px' }}>
            <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 12 }}>
              Zones ({zones.length})
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {zones.map(z => (
                <div key={z.id} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '8px 12px', background: 'var(--bg)', borderRadius: 7,
                }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 500 }}>{z.name}</div>
                    <div style={{ fontSize: 11, color: 'var(--muted)' }}>{z.type}</div>
                  </div>
                  <span style={{ fontSize: 16, fontFamily: 'Space Mono', fontWeight: 700, color: 'var(--accent)' }}>
                    {liveData?.zone_counts?.[z.name] ?? 0}
                  </span>
                </div>
              ))}
              {zones.length === 0 && (
                <div style={{ color: 'var(--muted)', fontSize: 12, textAlign: 'center', padding: '16px 0' }}>
                  No zones configured
                </div>
              )}
            </div>
          </div>

          {/* Expression summary */}
          <div style={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 12, padding: '18px 20px' }}>
            <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>Apparent Expressions</div>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 12 }}>
              Probabilistic visual cues only · Not biometric
            </div>
            {Object.entries(EXPR_LABELS).map(([key, info]) => (
              <div key={key} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <span style={{ fontSize: 12 }}>{info.label}</span>
                <span style={{ fontFamily: 'Space Mono', fontSize: 14, color: info.color, fontWeight: 700 }}>
                  {exprCounts[key] || 0}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Add Zone Modal */}
      {showAddZone && (
        <div style={{ position: 'fixed', inset: 0, background: '#00000080', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
          onClick={() => setShowAddZone(false)}>
          <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 14, padding: 32, width: 440 }}
            onClick={e => e.stopPropagation()}>
            <h2 style={{ margin: '0 0 20px', fontSize: 18 }}>Add Zone</h2>
            {[
              { key: 'name', label: 'Zone Name', placeholder: 'Counter Area' },
            ].map(f => (
              <div key={f.key} style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: 12, color: 'var(--muted)', marginBottom: 5, fontFamily: 'Space Mono' }}>{f.label}</label>
                <input value={zoneForm[f.key]} onChange={e => setZoneForm(p => ({ ...p, [f.key]: e.target.value }))}
                  placeholder={f.placeholder}
                  style={{ width: '100%', boxSizing: 'border-box', padding: '10px 12px', background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text)', fontSize: 14 }} />
              </div>
            ))}
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: 'block', fontSize: 12, color: 'var(--muted)', marginBottom: 5, fontFamily: 'Space Mono' }}>Type</label>
              <select value={zoneForm.type} onChange={e => setZoneForm(p => ({ ...p, type: e.target.value }))}
                style={{ width: '100%', padding: '10px 12px', background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text)', fontSize: 14 }}>
                {['entrance', 'counter', 'waiting', 'shared_area', 'room_area'].map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: 'block', fontSize: 12, color: 'var(--muted)', marginBottom: 5, fontFamily: 'Space Mono' }}>
                Polygon JSON [[x,y],...]
              </label>
              <textarea value={zoneForm.polygon_json} onChange={e => setZoneForm(p => ({ ...p, polygon_json: e.target.value }))}
                rows={3}
                style={{ width: '100%', boxSizing: 'border-box', padding: '10px 12px', background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text)', fontSize: 13, fontFamily: 'Space Mono', resize: 'vertical' }} />
            </div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 20 }}>
              <button onClick={() => setShowAddZone(false)} style={{ padding: '9px 18px', background: 'none', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--muted)', cursor: 'pointer' }}>Cancel</button>
              <button onClick={addZone} style={{ padding: '9px 18px', background: 'var(--accent)', border: 'none', borderRadius: 8, color: '#000', fontWeight: 700, cursor: 'pointer' }}>Create Zone</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
