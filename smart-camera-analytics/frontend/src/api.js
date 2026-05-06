const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const WS_BASE = import.meta.env.VITE_WS_URL || 'ws://localhost:8000'

async function get(path) {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`)
  return res.json()
}

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`)
  return res.json()
}

async function patch(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`)
  return res.json()
}

export const api = {
  // Dashboard
  overview: () => get('/api/dashboard/overview'),
  peopleCount: (cameraId) => get(`/api/dashboard/people-count${cameraId ? `?camera_id=${cameraId}` : ''}`),
  zoneAnalytics: (cameraId) => get(`/api/dashboard/zone-analytics${cameraId ? `?camera_id=${cameraId}` : ''}`),
  alerts: (params = {}) => {
    const q = new URLSearchParams(params).toString()
    return get(`/api/dashboard/alerts${q ? '?' + q : ''}`)
  },
  resolveAlert: (id) => post(`/api/alerts/${id}/resolve`),

  // Cameras
  cameras: (branchId) => get(`/api/cameras${branchId ? `?branch_id=${branchId}` : ''}`),
  camera: (id) => get(`/api/cameras/${id}`),
  createCamera: (data) => post('/api/cameras', data),
  updateCamera: (id, data) => patch(`/api/cameras/${id}`, data),
  cameraAnalytics: (id) => get(`/api/cameras/${id}/analytics`),

  // Branches
  branches: () => get('/api/branches'),
  createBranch: (data) => post('/api/branches', data),

  // Zones
  zones: (cameraId) => get(`/api/cameras/${cameraId}/zones`),
  createZone: (data) => post('/api/zones', data),

  // Audit
  auditLogs: (limit = 50) => get(`/api/audit-logs?limit=${limit}`),
}

export function createDashboardWS(onMessage) {
  const ws = new WebSocket(`${WS_BASE}/ws/dashboard`)
  ws.onopen = () => {
    console.log('WS connected')
    const ping = setInterval(() => ws.readyState === 1 && ws.send('ping'), 25000)
    ws._pingInterval = ping
  }
  ws.onmessage = (e) => {
    try { onMessage(JSON.parse(e.data)) } catch {}
  }
  ws.onclose = () => {
    clearInterval(ws._pingInterval)
    console.log('WS disconnected')
  }
  return ws
}

export function createCameraWS(cameraId, onMessage) {
  const ws = new WebSocket(`${WS_BASE}/ws/camera/${cameraId}`)
  ws.onopen = () => {
    const ping = setInterval(() => ws.readyState === 1 && ws.send('ping'), 25000)
    ws._pingInterval = ping
  }
  ws.onmessage = (e) => {
    try { onMessage(JSON.parse(e.data)) } catch {}
  }
  ws.onclose = () => clearInterval(ws._pingInterval)
  return ws
}
