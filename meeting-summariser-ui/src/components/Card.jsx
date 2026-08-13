import React from 'react';

export function Card({ children, style, className, ...rest }) {
  return (
    <div
      className={['app-card', className].filter(Boolean).join(' ')}
      style={{
        background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 16,
        padding: 24, boxShadow: '0 1px 0 rgba(17,17,17,0.03), 0 4px 12px rgba(17,17,17,0.03)',
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
}

export function SectionTitle({ children, subtitle }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <h3 style={{
        fontFamily: "'Manrope',sans-serif", fontWeight: 800, fontSize: 20,
        margin: 0, color: '#111',
      }}>{children}</h3>
      {subtitle && (
        <p style={{ margin: '4px 0 0', color: '#64748b', fontSize: 14 }}>{subtitle}</p>
      )}
    </div>
  );
}

export function Label({ children }) {
  return (
    <label style={{
      display: 'block', fontSize: 13.5, fontWeight: 600, color: '#334155',
      marginBottom: 6,
    }}>{children}</label>
  );
}

export function Button({ children, variant = 'primary', style, disabled, ...rest }) {
  const styles = {
    primary: {
      background: disabled ? '#94a3b8' : '#111', color: '#fff',
      boxShadow: disabled ? 'none' : '0 8px 20px rgba(17,17,17,0.18)',
    },
    teal: {
      background: disabled ? '#94a3b8' : '#0d9488', color: '#111',
      boxShadow: disabled ? 'none' : '0 8px 20px rgba(13,148,136,0.28)',
    },
    ghost: {
      background: 'transparent', color: '#111', border: '1px solid #e2e8f0',
    },
  }[variant];
  return (
    <button
      disabled={disabled}
      style={{
        borderRadius: 12, padding: '11px 22px', fontSize: 14.5, fontWeight: 700,
        border: 'none', cursor: disabled ? 'not-allowed' : 'pointer',
        transition: 'transform .15s ease, box-shadow .15s ease, opacity .15s ease',
        opacity: disabled ? 0.7 : 1,
        ...styles,
        ...style,
      }}
      {...rest}
    >{children}</button>
  );
}

export function ProgressBar({ value = 0, label }) {
  return (
    <div>
      {label && <div style={{ fontSize: 13, color: '#64748b', marginBottom: 6 }}>{label}</div>}
      <div style={{
        width: '100%', height: 8, background: '#e2e8f0', borderRadius: 999, overflow: 'hidden',
      }}>
        <div style={{
          width: `${Math.min(100, Math.max(0, value))}%`, height: '100%',
          background: 'linear-gradient(90deg,#0d9488,#14b8a6)', transition: 'width .3s ease',
        }} />
      </div>
    </div>
  );
}

export function Badge({ children, color = '#0d9488' }) {
  return (
    <span style={{
      display: 'inline-block', padding: '3px 10px', borderRadius: 999,
      fontSize: 11.5, fontWeight: 700, letterSpacing: '.05em', background: color,
      color: color === '#0d9488' ? '#111' : '#fff',
    }}>{children}</span>
  );
}
