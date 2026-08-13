import React, { useRef, useState } from 'react';
import { Card, SectionTitle, Label, Button } from './Card.jsx';

export default function ParticipantsContext({
  participants, onParticipantsChange,
  context, onContextChange,
  onSubmit, canSubmit, busy,
}) {
  const contextFileRef = useRef(null);

  const readContextFile = async (f) => {
    if (!f) return;
    const text = await f.text();
    onContextChange(text);
  };

  return (
    <Card>
      <SectionTitle subtitle="Confirm participants and add any prior meeting context, then generate the summary.">
        Participants & Context
      </SectionTitle>

      <div style={{ marginBottom: 16 }}>
        <Label>Participants (comma-separated)</Label>
        <input
          value={participants}
          onChange={(e) => onParticipantsChange(e.target.value)}
          placeholder="Alice, Bob, Charlie"
          style={inputStyle}
        />
        <div style={{ fontSize: 12.5, color: '#94a3b8', marginTop: 6 }}>
          Auto-filled from the transcript. Edit if needed.
        </div>
      </div>

      <div style={{ marginBottom: 8 }}>
        <Label>Prior information / meeting context (optional)</Label>
        <textarea
          value={context}
          onChange={(e) => onContextChange(e.target.value)}
          placeholder="e.g., Weekly engineering sync. Pay special attention to database migration tasks."
          style={{
            ...inputStyle, minHeight: 100, fontFamily: "'Inter', sans-serif",
            lineHeight: 1.5, resize: 'vertical',
          }}
        />
      </div>

      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 6 }}>
        <input
          ref={contextFileRef}
          type="file"
          accept=".txt"
          hidden
          onChange={(e) => readContextFile(e.target.files?.[0])}
        />
        <button
          onClick={() => contextFileRef.current?.click()}
          style={{
            background: 'transparent', border: '1px dashed #cbd5e1', color: '#64748b',
            padding: '8px 14px', borderRadius: 10, fontSize: 13, cursor: 'pointer',
          }}
        >📎 Upload context .txt</button>
        <div style={{ fontSize: 12.5, color: '#94a3b8' }}>
          Or paste directly above.
        </div>
      </div>

      <div style={{ marginTop: 24, display: 'flex', justifyContent: 'flex-end' }}>
        <Button onClick={onSubmit} disabled={!canSubmit || busy} variant="teal">
          {busy ? 'Generating…' : 'Generate Summary & Action Items'}
        </Button>
      </div>
    </Card>
  );
}

const inputStyle = {
  width: '100%', padding: '10px 12px', borderRadius: 10,
  border: '1px solid #cbd5e1', background: '#fff', fontSize: 14.5, color: '#111',
  outline: 'none', boxSizing: 'border-box',
};
