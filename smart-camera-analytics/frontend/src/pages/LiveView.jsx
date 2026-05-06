import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { api, createCameraWS } from '../api'

function CameraCard({ camera }) {
  const [liveData, setLiveData] = useState(null)
  const [wsStatus, setWsStatus] = useState('connecting')
  const wsRef = useRef(null)

  useEffect(() => {
    const ws = createCameraWS(camera.id, (msg) => {
      if (msg.type === 'live_update') {
        setLiveData(msg)
        setWsStatus('live')
      }
    })
    ws.onopen = () => setWsStatus('live')
    ws.onclose = () => setWsStatus('disconnected')
    wsRef.current = ws
    return () => ws.close()
  }, [camera.id])

  const persons = liveData?.tracked_persons || []
  const isOnline = camera.status === 'online'

  return (
    <div style={{
      background: 'var(--card)',
      border: '1px solid var(--border)',
      borderRadius: 14,
      overflow: 'hidden',
      display: 'flex',
      flexDirection: 'column',
      transition: 'border-color 0.2s',
    }}>
      {/* Card header */}
      <div style={{
        padding: '14px 18px',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 10,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
          <span style={{
            width: 9, height: 9, borderRadius: '50%', flexShrink: 0,
            background: isOnline ? '#00ff9d' : '#555',
            boxShadow: isOnline ? '0 0 8px #00ff9d' : 'none',
          }} />
          <span style={{
            fontWeight: 600, fontSize: 14, overflow: 'hidden',
            textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {camera.name}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
          <span style={{
            fontSize: 10, fontFamily: 'Space Mono', letterSpacing: 0.5,
            color: wsStatus === 'live' ? '#00ff9d' : '#888',
          }}>
            ● {wsStatus.toUpperCase()}
          </span>
          <Link to={`/cameras/${camera.id}`} style={{
            fontSize: 11, color: 'var(--accent)', textDecoration: 'none',
            background: 'var(--accent-bg)', borderRadius: 6, padding: '3px 8px',
            fontFamily: 'Space Mono',
          }}>
            DETAILS →
          </Link>
        </div>
      </div>

      {/* People count banner */}
      <div style={{
        padding: '18px 18px 10px',
        display: 'flex',
        alignItems: 'flex-end',
        gap: 8,
      }}>
        <span style={{
          fontSize: 42, fontWeight: 800, fontFamily: 'Space Mono',
          color: 'var(--accent)', lineHeight: 1,
        }}>
          {liveData?.people_count ?? 0}
        </span>
        <span style={{ fontSize: 13, color: 'var(--muted)', paddingBottom: 6 }}>
          people in frame
        </span>
      </div>

      {/* Zone counts */}
      {liveData?.zone_counts && Object.keys(liveData.zone_counts).length > 0 && (
        <div style={{
          margin: '0 18px 12px',
          display: 'flex', flexWrap: 'wrap', gap: 6,
        }}>
          {Object.entries(liveData.zone_counts).map(([zone, count]) => (
            <div key={zone} style={{
              background: 'var(--bg)', borderRadius: 6, padding: '4px 10px',
              fontSize: 12, display: 'flex', alignItems: 'center', gap: 6,
              border: '1px solid var(--border)',
            }}>
              <span style={{ color: 'var(--muted)' }}>{zone}</span>
              <span style={{ color: 'var(--accent)', fontFamily: 'Space Mono', fontWeight: 700 }}>{count}</span>
            </div>
          ))}
        </div>
      )}

      {/* Tracked persons list */}
      <div style={{
        flex: 1, margin: '0 18px 16px',
        background: 'var(--bg)', borderRadius: 10,
        border: '1px solid var(--border)',
        minHeight: 80, maxHeight: 160, overflowY: 'auto',
      }}>
        {persons.length === 0 ? (
          <div style={{
            color: 'var(--muted)', fontSize: 12, textAlign: 'center',
            padding: '24px 0',
          }}>
            {wsStatus === 'live' ? 'No persons detected' : 'Waiting for feed…'}
          </div>
        ) : (
          persons.map(p => (
            <div key={p.tracking_id} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '7px 12px', borderBottom: '1px solid var(--border)',
              fontSize: 12,
            }}>
              <span style={{
                fontFamily: 'Space Mono', fontSize: 11, color: 'var(--accent)',
                background: '#00ff9d12', borderRadius: 5, padding: '2px 6px',
              }}>
                {p.tracking_id}
              </span>
              <span style={{ color: 'var(--muted)' }}>
                {p.zone_name || '—'}
              </span>
              <span style={{ color: 'var(--muted)' }}>
                {Math.round(p.dwell_seconds ?? 0)}s
              </span>
            </div>
          ))
        )}
      </div>

      {/* Stream URL */}
      <div style={{
        padding: '8px 18px 14px',
        fontSize: 11, color: 'var(--muted)',
        fontFamily: 'Space Mono', overflow: 'hidden',
        textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>
        {camera.stream_url || 'No stream URL'}
      </div>
    </div>
  )
}

export default function LiveView() {
  const [cameras, setCameras] = useState([])
  const [loading, setLoading] = useState(true)
  const [cols, setCols] = useState(2)

  useEffect(() => {
    api.cameras().then(c => {
      setCameras(c)
      setLoading(false)
    }).catch(() => setLoading(false))

    const iv = setInterval(() => {
      api.cameras().then(setCameras).catch(() => {})
    }, 30000)
    return () => clearInterval(iv)
  }, [])

  const onlineCameras = cameras.filter(c => c.status === 'online').length

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1600, margin: '0 auto' }}>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700 }}>Live View</h1>
          <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 4 }}>
            {cameras.length} cameras &nbsp;·&nbsp;
            <span style={{ color: '#00ff9d' }}>● {onlineCameras} online</span>
          </div>
        </div>

        {/* Grid size toggle */}
        <div style={{ display: 'flex', gap: 6 }}>
          {[1, 2, 3].map(n => (
            <button
              key={n}
              onClick={() => setCols(n)}
              style={{
                width: 36, height: 36,
                background: cols === n ? 'var(--accent-bg)' : 'none',
                border: `1px solid ${cols === n ? 'var(--accent)' : 'var(--border)'}`,
                borderRadius: 8, cursor: 'pointer',
                color: cols === n ? 'var(--accent)' : 'var(--muted)',
                fontSize: 12, fontFamily: 'Space Mono',
              }}
            >
              {n}
            </button>
          ))}
        </div>
      </div>

      {/* Camera grid */}
      {loading ? (
        <div style={{ color: 'var(--muted)', textAlign: 'center', padding: '80px 0', fontSize: 14 }}>
          Loading cameras…
        </div>
      ) : cameras.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: '80px 0',
          color: 'var(--muted)', fontSize: 14,
        }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>◎</div>
          No cameras configured yet.&nbsp;
          <Link to="/cameras" style={{ color: 'var(--accent)' }}>Add a camera</Link>
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${cols}, 1fr)`,
          gap: 20,
        }}>
          {cameras.map(cam => (
            <CameraCard key={cam.id} camera={cam} />
          ))}
        </div>
      )}
    </div>
  )
}
