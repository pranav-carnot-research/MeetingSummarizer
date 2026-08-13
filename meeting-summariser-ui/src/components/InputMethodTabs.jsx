import React from 'react';
import { Upload, Mic, FileText, FileUp } from 'lucide-react';

const METHODS = [
  { id: 'audio', label: 'Upload Audio', icon: Upload },
  { id: 'realtime', label: 'Real-Time Audio', icon: Mic },
  { id: 'paste', label: 'Paste Transcript', icon: FileText },
  { id: 'text', label: 'Upload Transcript', icon: FileUp },
];

export default function InputMethodTabs({ value, onChange }) {
  return (
    <div className="app-input-method-tabs" style={{
      display: 'flex', gap: 8, background: '#f1f5f9', padding: 6,
      borderRadius: 14, border: '1px solid #e2e8f0',
      overflowX: 'auto', WebkitOverflowScrolling: 'touch',
    }}>
      {METHODS.map((m) => {
        const active = value === m.id;
        const Icon = m.icon;
        return (
          <button
            key={m.id}
            onClick={() => onChange(m.id)}
            className={`app-input-tab-btn${active ? ' is-active' : ''}`}
            style={{
              flex: '1 0 auto', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              padding: '11px 16px', borderRadius: 10, border: 'none', cursor: 'pointer',
              background: active ? '#111111' : 'transparent',
              color: active ? '#ffffff' : '#64748b',
              fontSize: 14.5, fontWeight: 600,
              whiteSpace: 'nowrap',
              transition: 'background .15s ease, color .15s ease',
            }}
          >
            <Icon size={16} />
            {m.label}
          </button>
        );
      })}
    </div>
  );
}
