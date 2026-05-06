import { BrowserRouter, Routes, Route, NavLink, Navigate, useLocation } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { AuthProvider, useAuth } from './context/AuthContext'
import Dashboard from './pages/Dashboard'
import Cameras from './pages/Cameras'
import CameraView from './pages/CameraView'
import Alerts from './pages/Alerts'
import LiveView from './pages/LiveView'
import Login from './pages/Login'
import ChangePassword from './pages/ChangePassword'
import { api } from './api'

const NAV = [
  { to: '/',        label: 'Dashboard', icon: '⬡', permission: 'analytics.view' },
  { to: '/cameras', label: 'Cameras',   icon: '◎', permission: 'cameras.view'   },
  { to: '/live',    label: 'Live View', icon: '▶', permission: 'cameras.view'   },
  { to: '/alerts',  label: 'Alerts',    icon: '◈', permission: 'alerts.view'    },
]

const ROLE_COLORS = {
  super_admin:        '#ff4d6d',
  admin:              '#00ff9d',
  branch_manager:     '#00b4d8',
  operations_manager: '#ffd166',
  receptionist:       '#a8dadc',
  viewer:             '#888',
}

function Sidebar({ cameras }) {
  const { user, logout, hasPermission } = useAuth()

  return (
    <nav style={{
      width: 220, minHeight: '100vh', background: 'var(--sidebar)',
      borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column',
      padding: '0 0 16px', flexShrink: 0,
    }}>
      {/* Logo */}
      <div style={{ padding: '24px 20px 20px', borderBottom: '1px solid var(--border)' }}>
        <div style={{ fontFamily: 'Space Mono', fontWeight: 700, fontSize: 13, color: 'var(--accent)', letterSpacing: 2 }}>
          SCA·SYSTEM
        </div>
        <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 3, letterSpacing: 1 }}>
          SMART CAMERA ANALYTICS
        </div>
      </div>

      {/* Main nav */}
      <div style={{ padding: '16px 12px', flex: 1 }}>
        <div style={{ fontSize: 10, color: 'var(--muted)', fontFamily: 'Space Mono', letterSpacing: 1, padding: '0 8px 8px' }}>
          NAVIGATION
        </div>
        {NAV.filter(n => hasPermission(n.permission)).map(({ to, label, icon }) => (
          <NavLink key={to} to={to} end={to === '/'} style={({ isActive }) => ({
            display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px',
            borderRadius: 8, marginBottom: 2, textDecoration: 'none', fontSize: 14,
            color: isActive ? 'var(--accent)' : 'var(--muted)',
            background: isActive ? 'var(--accent-bg)' : 'transparent',
            fontWeight: isActive ? 600 : 400,
            transition: 'all 0.15s',
          })}>
            <span style={{ fontSize: 16 }}>{icon}</span>
            {label}
          </NavLink>
        ))}

        {/* Cameras submenu */}
        {cameras.length > 0 && hasPermission('cameras.view') && (
          <div style={{ marginTop: 20 }}>
            <div style={{ fontSize: 10, color: 'var(--muted)', fontFamily: 'Space Mono', letterSpacing: 1, padding: '0 8px 8px' }}>
              LIVE CAMERAS
            </div>
            {cameras.map(cam => (
              <NavLink key={cam.id} to={`/cameras/${cam.id}`} style={({ isActive }) => ({
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '8px 12px', borderRadius: 7, marginBottom: 2, textDecoration: 'none',
                fontSize: 12, color: isActive ? 'var(--text)' : 'var(--muted)',
                background: isActive ? 'var(--accent-bg)' : 'transparent',
                transition: 'all 0.15s',
              })}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{
                    width: 7, height: 7, borderRadius: '50%',
                    background: cam.status === 'online' ? '#00ff9d' : '#555',
                    display: 'inline-block',
                    boxShadow: cam.status === 'online' ? '0 0 6px #00ff9d' : 'none',
                    flexShrink: 0,
                  }} />
                  {cam.name}
                </span>
              </NavLink>
            ))}
          </div>
        )}
      </div>

      {/* Privacy badge */}
      <div style={{ margin: '0 12px 12px', padding: '10px 12px', background: '#00b4d810', border: '1px solid #00b4d825', borderRadius: 8 }}>
        <div style={{ fontSize: 10, color: '#00b4d8', fontFamily: 'Space Mono', letterSpacing: 0.5 }}>🔒 PRIVACY-FIRST</div>
        <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 3, lineHeight: 1.4 }}>
          No face recognition<br/>No identity stored<br/>Temp IDs only
        </div>
      </div>

      {/* User card + logout */}
      {user && (
        <div style={{ margin: '0 12px', padding: '10px 12px', background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {user.name}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 4 }}>
            <span style={{
              fontSize: 10, fontFamily: 'Space Mono',
              color: ROLE_COLORS[user.role] || '#888',
              background: `${ROLE_COLORS[user.role] || '#888'}15`,
              borderRadius: 4, padding: '2px 6px',
            }}>
              {user.role.replace('_', ' ')}
            </span>
            <button onClick={logout} style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--muted)', fontSize: 11, padding: 0,
            }} title="Sign out">
              ⏻ out
            </button>
          </div>
        </div>
      )}
    </nav>
  )
}

function ProtectedRoute({ children }) {
  const { isAuthenticated, user } = useAuth()
  const location = useLocation()

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }
  if (user?.must_change_pw) {
    return <Navigate to="/change-password" replace />
  }
  return children
}

function AppShell() {
  const [cameras, setCameras] = useState([])
  const { isAuthenticated } = useAuth()

  useEffect(() => {
    if (!isAuthenticated) return
    api.cameras().then(setCameras).catch(() => {})
    const iv = setInterval(() => api.cameras().then(setCameras).catch(() => {}), 30000)
    return () => clearInterval(iv)
  }, [isAuthenticated])

  return (
    <Routes>
      <Route path="/login"           element={<Login />} />
      <Route path="/change-password" element={<ChangePassword />} />

      <Route path="/*" element={
        <ProtectedRoute>
          <div style={{ display: 'flex', minHeight: '100vh' }}>
            <Sidebar cameras={cameras} />
            <main style={{ flex: 1, overflow: 'auto', background: 'var(--bg)' }}>
              <Routes>
                <Route path="/"           element={<Dashboard />} />
                <Route path="/cameras"    element={<Cameras />} />
                <Route path="/cameras/:id" element={<CameraView />} />
                <Route path="/live"       element={<LiveView />} />
                <Route path="/alerts"     element={<Alerts />} />
              </Routes>
            </main>
          </div>
        </ProtectedRoute>
      } />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppShell />
      </AuthProvider>
    </BrowserRouter>
  )
}
