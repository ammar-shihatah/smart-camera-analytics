import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Login() {
  const { login } = useAuth()
  const navigate  = useNavigate()
  const location  = useLocation()
  const from      = location.state?.from?.pathname || '/'

  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [showPw, setShowPw]     = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const user = await login(email, password)
      if (user.must_change_pw) {
        navigate('/change-password', { replace: true })
      } else {
        navigate(from, { replace: true })
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'var(--bg)',
    }}>
      <div style={{ width: 400, maxWidth: '90vw' }}>

        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
          <div style={{
            fontFamily: 'Space Mono', fontWeight: 700, fontSize: 18,
            color: 'var(--accent)', letterSpacing: 3,
          }}>
            SCA·SYSTEM
          </div>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4, letterSpacing: 2 }}>
            SMART CAMERA ANALYTICS
          </div>
        </div>

        {/* Card */}
        <div style={{
          background: 'var(--card)', border: '1px solid var(--border)',
          borderRadius: 16, padding: 36,
        }}>
          <h1 style={{ margin: '0 0 6px', fontSize: 22, fontWeight: 700 }}>Sign in</h1>
          <p style={{ margin: '0 0 28px', color: 'var(--muted)', fontSize: 13 }}>
            Enter your credentials to continue
          </p>

          {error && (
            <div style={{
              background: '#ff4d6d15', border: '1px solid #ff4d6d40',
              borderRadius: 8, padding: '10px 14px', marginBottom: 20,
              fontSize: 13, color: '#ff4d6d',
            }}>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: 16 }}>
              <label style={{
                display: 'block', fontSize: 12, color: 'var(--muted)',
                fontFamily: 'Space Mono', letterSpacing: 0.5, marginBottom: 6,
              }}>EMAIL</label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="admin@sca.local"
                required
                autoFocus
                style={{
                  width: '100%', boxSizing: 'border-box',
                  padding: '11px 14px', background: 'var(--bg)',
                  border: '1px solid var(--border)', borderRadius: 8,
                  color: 'var(--text)', fontSize: 14, outline: 'none',
                }}
              />
            </div>

            <div style={{ marginBottom: 24 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <label style={{
                  fontSize: 12, color: 'var(--muted)',
                  fontFamily: 'Space Mono', letterSpacing: 0.5,
                }}>PASSWORD</label>
                <a
                  href="/forgot-password"
                  onClick={e => { e.preventDefault(); navigate('/forgot-password') }}
                  style={{ fontSize: 12, color: 'var(--accent)', textDecoration: 'none' }}
                >
                  Forgot password?
                </a>
              </div>
              <div style={{ position: 'relative' }}>
                <input
                  type={showPw ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  style={{
                    width: '100%', boxSizing: 'border-box',
                    padding: '11px 44px 11px 14px', background: 'var(--bg)',
                    border: '1px solid var(--border)', borderRadius: 8,
                    color: 'var(--text)', fontSize: 14, outline: 'none',
                  }}
                />
                <button
                  type="button"
                  onClick={() => setShowPw(p => !p)}
                  style={{
                    position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: 'var(--muted)', fontSize: 14, padding: 0,
                  }}
                >
                  {showPw ? '🙈' : '👁'}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              style={{
                width: '100%', padding: '12px',
                background: loading ? '#00ff9d80' : 'var(--accent)',
                border: 'none', borderRadius: 8,
                color: '#000', fontWeight: 700, fontSize: 15,
                cursor: loading ? 'not-allowed' : 'pointer',
                transition: 'opacity 0.15s',
              }}
            >
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </div>

        {/* Privacy note */}
        <div style={{ textAlign: 'center', marginTop: 20, fontSize: 11, color: 'var(--muted)' }}>
          🔒 Privacy-first · No face recognition for customers · Encrypted data
        </div>
      </div>
    </div>
  )
}
