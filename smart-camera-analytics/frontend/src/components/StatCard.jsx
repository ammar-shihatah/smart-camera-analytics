export default function StatCard({ label, value, unit = '', icon, color = '#00ff9d', trend, small }) {
  return (
    <div style={{
      background: 'var(--card)',
      border: '1px solid var(--border)',
      borderRadius: 12,
      padding: small ? '16px 20px' : '22px 26px',
      position: 'relative',
      overflow: 'hidden',
      transition: 'border-color 0.2s',
    }}
    onMouseEnter={e => e.currentTarget.style.borderColor = color}
    onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
    >
      {/* Glow accent */}
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0, height: 2,
        background: `linear-gradient(90deg, transparent, ${color}, transparent)`,
        opacity: 0.7,
      }} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ color: 'var(--muted)', fontSize: 11, fontFamily: 'Space Mono', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 8 }}>
            {label}
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
            <span style={{ fontSize: small ? 28 : 36, fontWeight: 700, color: 'var(--text)', fontFamily: 'Space Mono', lineHeight: 1 }}>
              {value ?? '—'}
            </span>
            {unit && <span style={{ color: 'var(--muted)', fontSize: 14 }}>{unit}</span>}
          </div>
          {trend != null && (
            <div style={{ marginTop: 6, fontSize: 12, color: trend >= 0 ? '#00ff9d' : '#ff4d6d' }}>
              {trend >= 0 ? '↑' : '↓'} {Math.abs(trend)}%
            </div>
          )}
        </div>
        {icon && (
          <div style={{
            width: 44, height: 44, borderRadius: 10,
            background: `${color}18`,
            border: `1px solid ${color}30`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 22, flexShrink: 0,
          }}>
            {icon}
          </div>
        )}
      </div>
    </div>
  )
}
