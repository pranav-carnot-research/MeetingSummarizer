import React from 'react';
import { AudioLines, ScrollText, Gauge, ClipboardList, Lock } from 'lucide-react';

// Horizontal tab bar shown at the top of the main pane whenever the current
// view is one of the four result views. Underline-style, sits directly under
// the page header. Final Report tab locks until a summary is generated.
const TABS = [
  { id: 'audio-player', label: 'Audio',                 icon: AudioLines,    requires: 'transcript' },
  { id: 'confidence',   label: 'Confidence Scores',     icon: Gauge,         requires: 'transcript' },
  { id: 'transcript',   label: 'Transcript & Playback', icon: ScrollText,    requires: 'transcript' },
  { id: 'report',       label: 'Final Report',          icon: ClipboardList, requires: 'summary' },
];

export default function ResultsTabs({ activeView, onNavigate, hasSummary }) {
  return (
    <div className="app-results-tabs" style={{
      display: 'flex', gap: 4, borderBottom: '1px solid #e2e8f0',
      marginBottom: 22, overflowX: 'auto',
    }}>
      {TABS.map((t) => {
        const disabled = t.requires === 'summary' && !hasSummary;
        const active = activeView === t.id;
        return (
          <Tab
            key={t.id}
            icon={t.icon}
            label={t.label}
            active={active}
            disabled={disabled}
            onClick={() => !disabled && onNavigate(t.id)}
          />
        );
      })}
    </div>
  );
}

function Tab({ icon: Icon, label, active, disabled, onClick }) {
  const [hover, setHover] = React.useState(false);
  const fg = active ? '#0f172a' : disabled ? '#cbd5e1' : (hover ? '#0f172a' : '#64748b');
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 7,
        padding: '11px 16px', border: 'none', background: 'transparent',
        color: fg,
        borderBottom: active ? '2.5px solid #0d9488' : '2.5px solid transparent',
        marginBottom: -1,
        fontSize: 13.5, fontWeight: active ? 700 : 600,
        cursor: disabled ? 'not-allowed' : 'pointer',
        whiteSpace: 'nowrap',
        transition: 'color .12s ease, border-color .12s ease',
      }}
    >
      {disabled ? <Lock size={13} /> : <Icon size={14} />}
      {label}
    </button>
  );
}
