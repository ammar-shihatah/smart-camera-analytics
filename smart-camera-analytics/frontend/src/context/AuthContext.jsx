import { createContext, useContext, useState, useEffect, useCallback } from 'react'

const AuthContext = createContext(null)

const TOKEN_KEY = 'sca_token'
const USER_KEY  = 'sca_user'

export function AuthProvider({ children }) {
  const [token, setToken]   = useState(() => localStorage.getItem(TOKEN_KEY))
  const [user, setUser]     = useState(() => {
    try { return JSON.parse(localStorage.getItem(USER_KEY)) } catch { return null }
  })
  const [loading, setLoading] = useState(false)

  const isAuthenticated = !!token && !!user

  const login = useCallback(async (email, password) => {
    const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'
    const res = await fetch(`${BASE}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      const detail = err.detail
      const msg = Array.isArray(detail)
        ? detail.map(d => d.msg || JSON.stringify(d)).join(', ')
        : typeof detail === 'string' ? detail : 'Login failed'
      throw new Error(msg)
    }
    const data = await res.json()
    localStorage.setItem(TOKEN_KEY, data.access_token)
    localStorage.setItem(USER_KEY, JSON.stringify(data.user))
    setToken(data.access_token)
    setUser(data.user)
    return data.user
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    setToken(null)
    setUser(null)
  }, [])

  const refreshMe = useCallback(async () => {
    if (!token) return
    try {
      const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'
      const res = await fetch(`${BASE}/api/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.status === 401) { logout(); return }
      const u = await res.json()
      localStorage.setItem(USER_KEY, JSON.stringify(u))
      setUser(u)
    } catch {}
  }, [token, logout])

  // Validate token on mount
  useEffect(() => {
    if (token) refreshMe()
  }, []) // eslint-disable-line

  const hasPermission = useCallback((permission) => {
    if (!user) return false
    const ROLE_PERMISSIONS = {
      super_admin:        ['*'],
      admin:              ['users.view','users.create','users.update','users.delete','branches.view','branches.create','branches.update','cameras.view','cameras.manage','zones.view','zones.manage','analytics.view','reports.export','alerts.view','alerts.resolve','employees.view','employees.manage','audit.view'],
      branch_manager:     ['branches.view','cameras.view','cameras.manage','zones.view','zones.manage','analytics.view','reports.export','alerts.view','alerts.resolve','employees.view'],
      operations_manager: ['branches.view','cameras.view','zones.view','analytics.view','reports.export','alerts.view','alerts.resolve'],
      receptionist:       ['branches.view','analytics.view','alerts.view'],
      viewer:             ['branches.view','cameras.view','zones.view','analytics.view','alerts.view'],
    }
    const perms = ROLE_PERMISSIONS[user.role] || []
    return perms.includes('*') || perms.includes(permission)
  }, [user])

  return (
    <AuthContext.Provider value={{ user, token, isAuthenticated, loading, login, logout, hasPermission, refreshMe }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
