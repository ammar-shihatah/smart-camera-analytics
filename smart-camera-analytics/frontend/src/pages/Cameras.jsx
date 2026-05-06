import { useState, useEffect } from 'react'
import { api } from '../api'

const STATUS_COLORS = { online: '#00ff9d', offline: '#888', error: '#ff4d6d', maintenance: '#ffd166' }

export default function Cameras() {
  const [cameras, setCameras] = useState([])
  const [branches, setBranches] = useState([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [showAddBranch, setShowAddBranch] = useState(false)
  const [branchForm, setBranchForm] = useState({ name: '', location: '' })
  const [form, setForm] = useState({ branch_id: '', name: '', stream_url: '', status: 'offline' })

  const load = async () => {
    try {
      const [cams, brs] = await Promise.all([api.cameras(), api.branches()])
      setCameras(cams)
      setBranches(brs)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const addBranch = async () => {
    if (!branchForm.name) return
    try {
      const newBranch = await api.createBranch(branchForm)
      setShowAddBranch(false)
      setBranchForm({ name: '', location: '' })
      await load()
      setForm(p => ({ ...p, branch_id: String(newBranch.id) }))
    } catch (e) {
      alert('Failed to create branch: ' + e.message)
    }
  }

  const addCamera = async () => {
    if (!form.name || !form.branch_id) return
    try {
      await api.createCamera({ ...form, branch_id: parseInt(form.branch_id) })
      setShowAdd(false)
      setForm({ branch_id: '', name: '', stream_url: '', status: 'offline' })
      load()
    } catch (e) {
      alert('Failed to create camera: ' + e.message)
    }
  }

  const updateStatus = async (id, status) => {
    await api.updateCamera(id, { status })
    load()
  }

  const branchName = (id) => branches.find(b => b.id === id)?.name || `Branch ${id}`

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26, fontWeight: 700 }}>Cameras</h1>
          <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 4 }}>
            Manage camera feeds and stream configurations
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button onClick={() => setShowAddBranch(true)} style={{
            background: 'none', color: 'var(--text)', border: '1px solid var(--border)',
            borderRadius: 8, padding: '10px 20px', fontWeight: 600, cursor: 'pointer', fontSize: 14,
          }}>+ Add Branch</button>
          <button onClick={() => setShowAdd(true)} style={{
            background: 'var(--accent)', color: '#000', border: 'none',
            borderRadius: 8, padding: '10px 20px', fontWeight: 700, cursor: 'pointer', fontSize: 14,
          }}>+ Add Camera</button>
        </div>
      </div>

      {/* Add Branch modal */}
      {showAddBranch && (
        <div style={{
          position: 'fixed', inset: 0, background: '#00000080', zIndex: 100,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }} onClick={() => setShowAddBranch(false)}>
          <div style={{
            background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 14,
            padding: 32, width: 380, maxWidth: '90vw',
          }} onClick={e => e.stopPropagation()}>
            <h2 style={{ margin: '0 0 20px', fontSize: 18 }}>Add Branch</h2>
            {[
              { key: 'name', label: 'Branch Name', placeholder: 'Main Branch' },
              { key: 'location', label: 'Location', placeholder: 'Riyadh, KSA' },
            ].map(f => (
              <div key={f.key} style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: 12, color: 'var(--muted)', marginBottom: 5, fontFamily: 'Space Mono' }}>
                  {f.label}
                </label>
                <input
                  value={branchForm[f.key]} onChange={e => setBranchForm(p => ({ ...p, [f.key]: e.target.value }))}
                  placeholder={f.placeholder}
                  style={{ width: '100%', boxSizing: 'border-box', padding: '10px 12px', background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text)', fontSize: 14 }}
                />
              </div>
            ))}
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 20 }}>
              <button onClick={() => setShowAddBranch(false)} style={{ padding: '9px 18px', background: 'none', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--muted)', cursor: 'pointer' }}>Cancel</button>
              <button onClick={addBranch} style={{ padding: '9px 18px', background: 'var(--accent)', border: 'none', borderRadius: 8, color: '#000', fontWeight: 700, cursor: 'pointer' }}>Create Branch</button>
            </div>
          </div>
        </div>
      )}

      {/* Add Camera modal */}
      {showAdd && (
        <div style={{
          position: 'fixed', inset: 0, background: '#00000080', zIndex: 100,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }} onClick={() => setShowAdd(false)}>
          <div style={{
            background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 14,
            padding: 32, width: 420, maxWidth: '90vw',
          }} onClick={e => e.stopPropagation()}>
            <h2 style={{ margin: '0 0 20px', fontSize: 18 }}>Add Camera</h2>
            {[
              { key: 'name', label: 'Name', placeholder: 'Entrance Cam' },
              { key: 'stream_url', label: 'Stream URL', placeholder: 'rtsp://... or leave empty' },
            ].map(f => (
              <div key={f.key} style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: 12, color: 'var(--muted)', marginBottom: 5, fontFamily: 'Space Mono' }}>
                  {f.label}
                </label>
                <input
                  value={form[f.key]} onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))}
                  placeholder={f.placeholder}
                  style={{ width: '100%', boxSizing: 'border-box', padding: '10px 12px', background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text)', fontSize: 14 }}
                />
              </div>
            ))}
            <div style={{ marginBottom: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
                <label style={{ fontSize: 12, color: 'var(--muted)', fontFamily: 'Space Mono' }}>Branch</label>
                <button onClick={() => { setShowAdd(false); setShowAddBranch(true) }} style={{
                  fontSize: 11, color: 'var(--accent)', background: 'none', border: 'none',
                  cursor: 'pointer', padding: 0, fontFamily: 'Space Mono',
                }}>+ New Branch</button>
              </div>
              {branches.length === 0 ? (
                <div style={{
                  padding: '12px', background: '#ffd16610', border: '1px solid #ffd16640',
                  borderRadius: 8, fontSize: 12, color: '#ffd166', textAlign: 'center',
                }}>
                  No branches yet — create one first
                </div>
              ) : (
                <select value={form.branch_id} onChange={e => setForm(p => ({ ...p, branch_id: e.target.value }))}
                  style={{ width: '100%', padding: '10px 12px', background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text)', fontSize: 14 }}>
                  <option value="">Select branch...</option>
                  {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                </select>
              )}
            </div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 20 }}>
              <button onClick={() => setShowAdd(false)} style={{ padding: '9px 18px', background: 'none', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--muted)', cursor: 'pointer' }}>Cancel</button>
              <button onClick={addCamera} style={{ padding: '9px 18px', background: 'var(--accent)', border: 'none', borderRadius: 8, color: '#000', fontWeight: 700, cursor: 'pointer' }}>Create</button>
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <div style={{ color: 'var(--muted)', textAlign: 'center', padding: 60 }}>Loading cameras…</div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
          {cameras.map(cam => (
            <div key={cam.id} style={{
              background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 12, padding: '20px 22px',
              transition: 'border-color 0.2s',
            }}>
              {/* Status bar */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{
                    width: 9, height: 9, borderRadius: '50%',
                    background: STATUS_COLORS[cam.status] || '#888',
                    display: 'inline-block',
                    boxShadow: cam.status === 'online' ? '0 0 8px #00ff9d' : 'none',
                  }} />
                  <span style={{ fontSize: 11, color: STATUS_COLORS[cam.status], fontFamily: 'Space Mono' }}>
                    {cam.status.toUpperCase()}
                  </span>
                </div>
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>#{cam.id}</span>
              </div>

              <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 4 }}>{cam.name}</div>
              <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 12 }}>{branchName(cam.branch_id)}</div>

              {cam.stream_url && (
                <div style={{
                  fontSize: 11, color: 'var(--muted)', fontFamily: 'Space Mono',
                  background: 'var(--bg)', borderRadius: 6, padding: '6px 10px', marginBottom: 14,
                  wordBreak: 'break-all',
                }}>
                  {cam.stream_url}
                </div>
              )}

              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {['online', 'offline', 'maintenance'].map(s => (
                  <button key={s} onClick={() => updateStatus(cam.id, s)} style={{
                    padding: '5px 10px', fontSize: 11, borderRadius: 6, cursor: 'pointer',
                    background: cam.status === s ? `${STATUS_COLORS[s]}20` : 'none',
                    border: `1px solid ${cam.status === s ? STATUS_COLORS[s] : 'var(--border)'}`,
                    color: cam.status === s ? STATUS_COLORS[s] : 'var(--muted)',
                    fontFamily: 'Space Mono',
                  }}>{s}</button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
