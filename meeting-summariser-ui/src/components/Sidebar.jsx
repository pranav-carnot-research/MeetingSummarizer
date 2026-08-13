import React from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowLeft, Plus, Upload, Mic, FileText, FileUp, ArrowRight, X,
} from 'lucide-react';

// Left navigation. Only INPUT lives here — the sidebar is the way to pick
// (or switch to) a capture method. Result views are surfaced as horizontal
// tabs inside the main pane instead, so this stays quiet and single-purpose.
//
// A single "Return to results" bridge appears below the INPUT list once
// there's a session to return to.
//
// Mobile: renders as an off-canvas drawer (see .app-sidebar rules in
// index.css). `open` toggles the translateX; `onClose` is wired to the
// X button + parent-owned backdrop.
export default function Sidebar({
  activeView,
  onNavigate,
  hasResults,
  onNewSession,
  onReturnToResults,
  open = false,
  onClose,
}) {
  const inputItems = [
    { id: 'audio',    label: 'Upload Audio',      icon: Upload },
    { id: 'realtime', label: 'Real-Time',         icon: Mic },
    { id: 'paste',    label: 'Paste Transcript',  icon: FileText },
    { id: 'text',     label: 'Upload Transcript', icon: FileUp },
  ];

  return (
    <aside
      className={`app-sidebar${open ? ' is-open' : ''}`}
      style={{
        position: 'sticky', top: 0, alignSelf: 'flex-start',
        height: '100vh',
        width: 260, flexShrink: 0,
        background: '#f8fafc', borderRight: '1px solid #e2e8f0',
        display: 'flex', flexDirection: 'column',
        padding: '22px 18px 18px',
        boxSizing: 'border-box',
        overflowY: 'auto',
      }}
    >
      {/* Mobile-only close button. Hidden on desktop via CSS. */}
      <button
        type="button"
        onClick={onClose}
        aria-label="Close menu"
        className="app-sidebar-close"
        style={{
          position: 'absolute', top: 10, right: 10,
          background: 'transparent', border: 'none', cursor: 'pointer',
          padding: 6, borderRadius: 8, color: '#475569',
          lineHeight: 0,
        }}
      >
        <X size={20} />
      </button>
      <div style={{ marginBottom: 20 }}>
        <Link
          to="/"
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            color: '#64748b', fontSize: 12.5, fontWeight: 500,
            textDecoration: 'none', padding: '4px 8px 4px 4px',
            borderRadius: 6, marginBottom: 12,
          }}
        >
          <ArrowLeft size={13} />
          Back to home
        </Link>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <img
            src="/icarkno%20logo.png"
            alt="icarKno"
            style={{
              width: 34, height: 34, flexShrink: 0,
              objectFit: 'contain', borderRadius: 9,
            }}
          />
          <div style={{
            fontFamily: "'Manrope',sans-serif", fontWeight: 800, fontSize: 15,
            color: '#0f172a', letterSpacing: '-0.01em',
          }}>Meeting Summariser</div>
        </div>
      </div>

      <button
        onClick={onNewSession}
        className="app-sidebar-newsession"
        style={{
          display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'center',
          width: '100%', padding: '10px 12px', marginBottom: 22,
          background: '#0f172a', color: '#fff',
          border: 'none', borderRadius: 10, cursor: 'pointer',
          fontSize: 13.5, fontWeight: 700,
          boxShadow: '0 4px 12px rgba(15,23,42,0.15)',
        }}
      >
        <Plus size={15} /> New Session
      </button>

      <NavGroup title="Input Method">
        {inputItems.map((it) => (
          <NavItem
            key={it.id}
            icon={it.icon}
            label={it.label}
            active={activeView === it.id}
            onClick={() => onNavigate(it.id)}
          />
        ))}
      </NavGroup>

      {hasResults && (
        <button
          onClick={onReturnToResults}
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '9px 12px', marginBottom: 16,
            background: 'rgba(13,148,136,0.10)', color: '#0f766e',
            border: '1px solid rgba(13,148,136,0.35)', borderRadius: 9,
            cursor: 'pointer', fontSize: 13, fontWeight: 700,
          }}
        >
          <ArrowRight size={14} />
          <span style={{ flex: 1, textAlign: 'left' }}>Return to results</span>
        </button>
      )}

      <div style={{ flex: 1 }} />

      <div className="app-sidebar-footer" style={{
        fontSize: 11.5, color: '#94a3b8', lineHeight: 1.55,
        borderTop: '1px solid #e2e8f0', paddingTop: 14,
      }}>
        Runs entirely on your infrastructure. Nothing leaves your network.
      </div>
    </aside>
  );
}

function NavGroup({ title, children }) {
  return (
    <div style={{ marginBottom: 22 }}>
      <div className="app-sidebar-group-title" style={{
        fontFamily: "'Manrope',sans-serif", fontSize: 11, fontWeight: 800,
        letterSpacing: '.14em', color: '#94a3b8', textTransform: 'uppercase',
        padding: '0 8px 8px',
      }}>{title}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {children}
      </div>
    </div>
  );
}

function NavItem({ icon: Icon, label, active, disabled, onClick }) {
  const [hover, setHover] = React.useState(false);
  const bg = active
    ? '#0f172a'
    : (hover && !disabled ? 'rgba(15,23,42,0.06)' : 'transparent');
  const fg = active ? '#fff' : (disabled ? '#cbd5e1' : '#334155');
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '9px 12px', border: 'none',
        borderRadius: 9, background: bg, color: fg,
        fontSize: 13.5, fontWeight: active ? 700 : 500,
        cursor: disabled ? 'not-allowed' : 'pointer',
        textAlign: 'left', width: '100%',
        transition: 'background .12s ease, color .12s ease',
      }}
    >
      <Icon size={15} />
      <span style={{ flex: 1 }}>{label}</span>
      {active && (
        <span style={{
          width: 6, height: 6, borderRadius: '50%', background: '#0d9488',
        }} />
      )}
    </button>
  );
}
