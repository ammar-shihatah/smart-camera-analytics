import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { api } from '../api'

export default function ChangePassword() {
  const { logout, refreshMe } = useAuth()
  const navigate = useNavigate()
  const [form, setForm]     = useState({ current_password: '', new_password: '', confirm: '' })
  const [error, setError]   = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    if (form.new_password !== form.confirm) {
      setError('New passwords do not match')
      return
    }
    if (form.new_password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }
    setLoading(true)
    try {
      await api.changePassword(form.current_password, form.new_password)
      await refreshMe()
      navigate('/', { replace: true })
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
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{ fontFamily: 'Space Mono', fontWeight: 700, fontSize: 18, color: 'var(--accent)', letterSpacing: 3 }}>
            SCA·SYSTEM
          </div>
        </div>

        <div style={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 16, padding: 36 }}>
          <div style={{ background: '#ffd16615', border: '1px solid #ffd16640', borderRadius: 8, padding: '10px 14px', marginBottom: 24, fontSize: 13, color: '#ffd166' }}>
            ⚠ You must change your password before continuing
          </div>

          <h1 style={{ margin: '0 0 24px', fontSize: 20, fontWeight: 700 }}>Set New Password</h1>

          {error && (
            <div style={{ background: '#ff4d6d15', border: '1px solid #ff4d6d40', borderRadius: 8, padding: '10px 14px', marginBottom: 16, fontSize: 13, color: '#ff4d6d' }}>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit}>
            {[
              { key: 'current_password', label: 'CURRENT PASSWORD', placeholder: '••••••••' },
              { key: 'new_password',     label: 'NEW PASSWORD',     placeholder: '8+ characters' },
              { key: 'confirm',          label: 'CONFIRM PASSWORD', placeholder: '••••••••' },
            ].map(f => (
              <div key={f.key} style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', fontSize: 12, color: 'var(--muted)', fontFamily: 'Space Mono', marginBottom: 6 }}>
                  {f.label}
                </label>
                <input
                  type="password"
                  value={form[f.key]}
                  onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))}
                  placeholder={f.placeholder}
                  required
                  style={{ width: '100%', boxSizing: 'border-box', padding: '11px 14px', background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text)', fontSize: 14 }}
                />
              </div>
            ))}
            <div style={{ display: 'flex', gap: 10, marginTop: 24 }}>
              <button type="button" onClick={logout} style={{ flex: 1, padding: '11px', background: 'none', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--muted)', cursor: 'pointer' }}>
                Logout
              </button>
              <button type="submit" disabled={loading} style={{ flex: 2, padding: '11px', background: 'var(--accent)', border: 'none', borderRadius: 8, color: '#000', fontWeight: 700, cursor: loading ? 'not-allowed' : 'pointer' }}>
                {loading ? 'Saving…' : 'Save Password'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
