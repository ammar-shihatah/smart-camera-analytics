import { useState, useEffect, useRef, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'

// ─── Single camera stream card ────────────────────────────────────────────────
function CameraStreamCard({ camera, cols }) {
  const [streamStatus, setStreamStatus] = useState('loading') // loading | live | error
  const [testResult, setTestResult]     = useState(null)
  const [testing, setTesting]           = useState(false)
  const [streamKey, setStreamKey]       = useState(0)   // bump to reload img
  const imgRef = useRef(null)

  const streamUrl = api.streamUrl(camera.id, { fps: 15, profile: 'stored', quality: 5 })

  // Detect when the first MJPEG frame loads
  const onImgLoad  = useCallback(() => setStreamStatus('live'), [])
  const onImgError = useCallback(() => setStreamStatus('error'), [])

  useEffect(() => {
    setStreamStatus('loading')
    setStreamKey(k => k + 1)
  }, [camera.id])

  const reload = () => {
    setStreamStatus('loading')
    setTestResult(null)
    setStreamKey(k => k + 1)
  }

  const testConnection = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const res = await api.testCameraConnection(camera.id)
      setTestResult(res)
      if (res.success) reload()
    } catch (e) {
      setTestResult({ success: false, error_message: e.message, connection_status: 'error' })
    } finally {
      setTesting(false)
    }
  }

  const isOnline = camera.status === 'online'
  const cardHeight = cols === 1 ? 520 : cols === 2 ? 380 : 280

  return (
    <div style={{
      background: 'var(--card)', border: `1px solid ${streamStatus === 'live' ? '#00ff9d30' : 'var(--border)'}`,
      borderRadius: 14, overflow: 'hidden', display: 'flex', flexDirection: 'column',
      transition: 'border-color 0.3s',
    }}>
      {/* Header */}
      <div style={{
        padding: '10px 14px', borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
          <span style={{
            width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
            background: isOnline ? '#00ff9d' : '#555',
            boxShadow: isOnline ? '0 0 6px #00ff9d' : 'none',
          }} />
          <span style={{ fontWeight: 600, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {camera.name}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          <StatusBadge status={streamStatus} />
          <Link to={`/cameras/${camera.id}`} style={{
            fontSize: 10, color: 'var(--accent)', textDecoration: 'none',
            background: 'var(--accent-bg)', borderRadius: 5, padding: '2px 7px',
            fontFamily: 'Space Mono',
          }}>DETAILS →</Link>
        </div>
      </div>

      {/* Stream area */}
      <div style={{
        position: 'relative', background: '#0a0a0a',
        height: cardHeight, overflow: 'hidden', flexShrink: 0,
      }}>
        {/* MJPEG img — always rendered, hidden while loading */}
        <img
          key={streamKey}
          ref={imgRef}
          src={streamUrl}
          onLoad={onImgLoad}
          onError={onImgError}
          alt={camera.name}
          style={{
            width: '100%', height: '100%', objectFit: 'contain',
            display: 'block',
          }}
        />

        {/* Loading overlay */}
        {streamStatus === 'loading' && (
          <div style={{
            position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center',
            background: '#0a0a0a',
          }}>
            <div style={{
              width: 36, height: 36, border: '3px solid #00ff9d30',
              borderTop: '3px solid #00ff9d', borderRadius: '50%',
              animation: 'spin 1s linear infinite',
            }} />
            <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 14 }}>
              Connecting to stream…
            </div>
          </div>
        )}

        {/* Error overlay */}
        {streamStatus === 'error' && (
          <div style={{
            position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center', gap: 10,
            background: '#0a0a0a',
          }}>
            <span style={{ fontSize: 32 }}>📷</span>
            <div style={{ color: '#ff4d6d', fontSize: 12, fontFamily: 'Space Mono' }}>
              STREAM UNAVAILABLE
            </div>
            {camera.last_error && (
              <div style={{ color: 'var(--muted)', fontSize: 11, maxWidth: 240, textAlign: 'center' }}>
                {camera.last_error}
              </div>
            )}
            <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
              <button onClick={reload} style={btnStyle('#333', 'var(--muted)')}>
                ↺ Retry
              </button>
              <button onClick={testConnection} disabled={testing} style={btnStyle('#00ff9d20', '#00ff9d')}>
                {testing ? 'Testing…' : '⚡ Test Connection'}
              </button>
            </div>
          </div>
        )}

        {/* Live badge overlay */}
        {streamStatus === 'live' && (
          <div style={{
            position: 'absolute', top: 8, right: 8,
            background: '#00000080', borderRadius: 6, padding: '3px 8px',
            display: 'flex', alignItems: 'center', gap: 5,
          }}>
            <span style={{
              width: 6, height: 6, borderRadius: '50%', background: '#ff3333',
              boxShadow: '0 0 6px #ff3333', flexShrink: 0,
            }} />
            <span style={{ fontSize: 10, color: '#fff', fontFamily: 'Space Mono' }}>LIVE</span>
          </div>
        )}
      </div>

      {/* Test result */}
      {testResult && (
        <div style={{
          margin: '10px 12px 0',
          background: testResult.success ? '#00ff9d10' : '#ff4d6d10',
          border: `1px solid ${testResult.success ? '#00ff9d30' : '#ff4d6d30'}`,
          borderRadius: 8, padding: '8px 12px', fontSize: 11,
        }}>
          <div style={{ color: testResult.success ? '#00ff9d' : '#ff4d6d', fontWeight: 600, marginBottom: 4 }}>
            {testResult.success ? '✓ Connection OK' : '✗ Connection Failed'}
            {testResult.connection_time_ms && ` — ${testResult.connection_time_ms}ms`}
            {testResult.resolution && ` — ${testResult.resolution}`}
          </div>
          {testResult.error_message && (
            <div style={{ color: 'var(--muted)', marginBottom: 3 }}>{testResult.error_message}</div>
          )}
          {testResult.suggested_fix && (
            <div style={{ color: '#ffd166' }}>💡 {testResult.suggested_fix}</div>
          )}
        </div>
      )}

      {/* Footer */}
      <div style={{
        padding: '8px 12px 10px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{
          fontSize: 10, color: 'var(--muted)', fontFamily: 'Space Mono',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '65%',
        }}>
          {camera.stream_url
            ? camera.stream_url.replace(/\/\/.*?@/, '//***@')   // mask credentials
            : 'No stream URL'}
        </div>
        <button onClick={testConnection} disabled={testing || streamStatus === 'live'} style={{
          ...btnStyle(testing ? '#333' : '#00ff9d15', testing ? 'var(--muted)' : '#00ff9d'),
          opacity: streamStatus === 'live' ? 0.4 : 1,
        }}>
          {testing ? 'Testing…' : '⚡ Test'}
        </button>
      </div>
    </div>
  )
}

function StatusBadge({ status }) {
  const map = {
    loading: { color: '#ffd166', label: 'CONNECTING' },
    live:    { color: '#00ff9d', label: 'LIVE' },
    error:   { color: '#ff4d6d', label: 'ERROR' },
  }
  const { color, label } = map[status] || map.error
  return (
    <span style={{ fontSize: 10, fontFamily: 'Space Mono', color }}>● {label}</span>
  )
}

const btnStyle = (bg, color) => ({
  background: bg, border: `1px solid ${color}40`,
  color, borderRadius: 6, padding: '4px 10px',
  fontSize: 11, cursor: 'pointer', fontFamily: 'Space Mono',
})


// ─── Main LiveView page ───────────────────────────────────────────────────────
export default function LiveView() {
  const [cameras, setCameras] = useState([])
  const [loading, setLoading] = useState(true)
  const [cols, setCols]       = useState(2)

  useEffect(() => {
    api.cameras().then(c => { setCameras(c); setLoading(false) }).catch(() => setLoading(false))
    const iv = setInterval(() => api.cameras().then(setCameras).catch(() => {}), 30000)
    return () => clearInterval(iv)
  }, [])

  const onlineCameras = cameras.filter(c => c.status === 'online').length

  return (
    <>
      {/* CSS for spinner */}
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>

      <div style={{ padding: '28px 32px', maxWidth: 1600, margin: '0 auto' }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28 }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700 }}>Live View</h1>
            <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 4 }}>
              {cameras.length} cameras &nbsp;·&nbsp;
              <span style={{ color: '#00ff9d' }}>● {onlineCameras} online</span>
              &nbsp;·&nbsp;
              <span style={{ color: 'var(--muted)', fontSize: 11 }}>
                Streams via RTSP→MJPEG proxy
              </span>
            </div>
          </div>

          {/* Grid size toggle */}
          <div style={{ display: 'flex', gap: 6 }}>
            {[1, 2, 3].map(n => (
              <button key={n} onClick={() => setCols(n)} style={{
                width: 36, height: 36,
                background: cols === n ? 'var(--accent-bg)' : 'none',
                border: `1px solid ${cols === n ? 'var(--accent)' : 'var(--border)'}`,
                borderRadius: 8, cursor: 'pointer',
                color: cols === n ? 'var(--accent)' : 'var(--muted)',
                fontSize: 12, fontFamily: 'Space Mono',
              }}>{n}</button>
            ))}
          </div>
        </div>

        {/* Info banner */}
        <div style={{
          background: '#00b4d810', border: '1px solid #00b4d825', borderRadius: 8,
          padding: '10px 16px', marginBottom: 20, fontSize: 12, color: '#00b4d8',
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <span>ℹ️</span>
          <span>
            The backend streams RTSP directly to your browser as MJPEG. If a camera shows an error,
            click <strong>⚡ Test</strong> to diagnose the connection from the server side.
          </span>
        </div>

        {loading ? (
          <div style={{ color: 'var(--muted)', textAlign: 'center', padding: '80px 0', fontSize: 14 }}>
            Loading cameras…
          </div>
        ) : cameras.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '80px 0', color: 'var(--muted)', fontSize: 14 }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>◎</div>
            No cameras configured.&nbsp;
            <Link to="/cameras" style={{ color: 'var(--accent)' }}>Add a camera</Link>
          </div>
        ) : (
          <div style={{
            display: 'grid',
            gridTemplateColumns: `repeat(${cols}, 1fr)`,
            gap: 16,
          }}>
            {cameras.map(cam => (
              <CameraStreamCard key={cam.id} camera={cam} cols={cols} />
            ))}
          </div>
        )}
      </div>
    </>
  )
}
