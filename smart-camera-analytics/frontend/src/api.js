const BASE    = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const WS_BASE = import.meta.env.VITE_WS_URL || 'ws://localhost:8000'

function getToken() {
  return localStorage.getItem('sca_token')
}

function authHeaders(extra = {}) {
  const token = getToken()
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  }
}

async function request(method, path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: authHeaders(),
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  })
  if (res.status === 401) {
    // Token expired — clear storage and redirect to login
    localStorage.removeItem('sca_token')
    localStorage.removeItem('sca_user')
    window.location.href = '/login'
    throw new Error('Session expired')
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `API ${res.status}: ${path}`)
  }
  return res.json()
}

const get   = (path)        => request('GET',   path)
const post  = (path, body)  => request('POST',  path, body)
const patch = (path, body)  => request('PATCH', path, body)
const del   = (path)        => request('DELETE', path)

export const api = {
  // Auth
  me:             ()              => get('/api/auth/me'),
  changePassword: (current, next) => post('/api/auth/change-password', { current_password: current, new_password: next }),
  forgotPassword: (email)         => post('/api/auth/forgot-password', { email }),
  resetPassword:  (token, pw)     => post('/api/auth/reset-password',  { token, new_password: pw }),

  // Users
  users:        ()           => get('/api/users'),
  createUser:   (data)       => post('/api/users', data),
  updateUser:   (id, data)   => patch(`/api/users/${id}`, data),
  deleteUser:   (id)         => del(`/api/users/${id}`),

  // Dashboard
  overview:     ()           => get('/api/dashboard/overview'),
  peopleCount:  (cameraId)   => get(`/api/dashboard/people-count${cameraId ? `?camera_id=${cameraId}` : ''}`),
  zoneAnalytics:(cameraId)   => get(`/api/dashboard/zone-analytics${cameraId ? `?camera_id=${cameraId}` : ''}`),
  alerts:       (params = {}) => {
    const q = new URLSearchParams(params).toString()
    return get(`/api/dashboard/alerts${q ? '?' + q : ''}`)
  },
  resolveAlert: (id)         => post(`/api/alerts/${id}/resolve`),

  // Cameras
  cameras:               (branchId) => get(`/api/cameras${branchId ? `?branch_id=${branchId}` : ''}`),
  camera:                (id)       => get(`/api/cameras/${id}`),
  createCamera:          (data)     => post('/api/cameras', data),
  updateCamera:          (id, data) => patch(`/api/cameras/${id}`, data),
  cameraAnalytics:       (id)       => get(`/api/cameras/${id}/analytics`),
  testCameraConnection:  (id)       => get(`/api/cameras/${id}/test-connection`),
  streamUrl:             (id)       => {
    const token = localStorage.getItem('sca_token')
    const BASE  = import.meta.env.VITE_API_URL || 'http://localhost:8000'
    return `${BASE}/api/cameras/${id}/stream?token=${token}&fps=15`
  },

  // Branches
  branches:     ()      => get('/api/branches'),
  createBranch: (data)  => post('/api/branches', data),

  // Zones
  zones:        (cameraId) => get(`/api/cameras/${cameraId}/zones`),
  createZone:   (data)     => post('/api/zones', data),

  // Audit
  auditLogs:    (limit = 50) => get(`/api/audit-logs?limit=${limit}`),
}

function wsUrl(path) {
  const token = getToken()
  return `${WS_BASE}${path}${token ? `?token=${token}` : ''}`
}

export function createDashboardWS(onMessage) {
  const ws = new WebSocket(wsUrl('/ws/dashboard'))
  ws.onopen = () => {
    const ping = setInterval(() => ws.readyState === 1 && ws.send('ping'), 25000)
    ws._pingInterval = ping
  }
  ws.onmessage = (e) => { try { onMessage(JSON.parse(e.data)) } catch {} }
  ws.onclose = () => { clearInterval(ws._pingInterval) }
  return ws
}

export function createCameraWS(cameraId, onMessage) {
  const ws = new WebSocket(wsUrl(`/ws/camera/${cameraId}`))
  ws.onopen = () => {
    const ping = setInterval(() => ws.readyState === 1 && ws.send('ping'), 25000)
    ws._pingInterval = ping
  }
  ws.onmessage = (e) => { try { onMessage(JSON.parse(e.data)) } catch {} }
  ws.onclose = () => clearInterval(ws._pingInterval)
  return ws
}
