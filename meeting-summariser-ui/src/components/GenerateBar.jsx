import React, { useRef, useState } from 'react';
import { Sparkles, Plus, X, Paperclip, ChevronDown, ChevronUp } from 'lucide-react';

// Slim "ready to summarise" bar. Replaces the old ParticipantsContext modal.
// Participants shown as editable chips; context is a collapsible textarea.
// The Generate Summary button is the primary CTA.
export default function GenerateBar({
  participants, onParticipantsChange,
  context, onContextChange,
  isLongRecording, onLongRecordingChange,
  onSubmit, canSubmit, busy,
  progress, statusMessage,
  hasSummary,
}) {
  const [contextOpen, setContextOpen] = useState(!!context);
  const [chipDraft, setChipDraft] = useState('');
  const contextFileRef = useRef(null);

  const chips = (participants || '')
    .split(',').map((s) => s.trim()).filter(Boolean);

  const setChips = (arr) => onParticipantsChange(arr.join(', '));
  const addChip = (name) => {
    const v = name.trim();
    if (!v) return;
    if (chips.some((c) => c.toLowerCase() === v.toLowerCase())) return;
    setChips([...chips, v]);
    setChipDraft('');
  };
  const removeChip = (i) => setChips(chips.filter((_, idx) => idx !== i));

  const readContextFile = async (f) => {
    if (!f) return;
    const text = await f.text();
    onContextChange(text);
    setContextOpen(true);
  };

  return (
    <div style={{
      background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 14,
      padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 12,
      boxShadow: '0 2px 6px rgba(17,17,17,0.04)',
    }}>
      {/* Row 1: participants + CTA */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
        <div style={{
          fontSize: 11.5, fontWeight: 800, letterSpacing: '.12em',
          color: '#94a3b8', textTransform: 'uppercase', whiteSpace: 'nowrap',
        }}>Participants</div>

        <div style={{
          display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6,
          flex: 1, minWidth: 220,
        }}>
          {chips.map((name, i) => (
            <span key={i} style={{
              display: 'inline-flex', alignItems: 'center', gap: 5,
              background: '#f1f5f9', border: '1px solid #e2e8f0',
              borderRadius: 999, padding: '4px 4px 4px 10px',
              fontSize: 13, color: '#111',
            }}>
              {name}
              <button
                onClick={() => removeChip(i)}
                aria-label={`Remove ${name}`}
                style={{
                  width: 18, height: 18, borderRadius: '50%', border: 'none',
                  background: 'transparent', cursor: 'pointer', color: '#64748b',
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                }}
              ><X size={11} /></button>
            </span>
          ))}
          <input
            value={chipDraft}
            onChange={(e) => setChipDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addChip(chipDraft); }
              else if (e.key === 'Backspace' && !chipDraft && chips.length) {
                removeChip(chips.length - 1);
              }
            }}
            onBlur={() => addChip(chipDraft)}
            placeholder={chips.length ? 'Add…' : 'Add a name and press Enter'}
            style={{
              flex: 1, minWidth: 140, padding: '5px 8px', border: 'none',
              background: 'transparent', outline: 'none', fontSize: 13.5,
            }}
          />
        </div>

        <button
          onClick={onSubmit}
          disabled={!canSubmit || busy}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 8,
            background: (!canSubmit || busy) ? '#cbd5e1' : '#0d9488',
            color: '#0f172a', border: 'none', borderRadius: 11,
            padding: '11px 20px', fontSize: 14, fontWeight: 800,
            cursor: (!canSubmit || busy) ? 'not-allowed' : 'pointer',
            boxShadow: (!canSubmit || busy) ? 'none' : '0 6px 16px rgba(13,148,136,0.28)',
            transition: 'background .15s ease, box-shadow .15s ease',
            whiteSpace: 'nowrap',
          }}
        >
          <Sparkles size={15} />
          {busy ? 'Generating…' : hasSummary ? 'Regenerate Summary' : 'Generate Summary'}
        </button>
      </div>

      {/* Row 2: context toggle + long-recording toggle */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
        <button
          onClick={() => setContextOpen((v) => !v)}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            background: 'transparent', border: '1px dashed #cbd5e1',
            padding: '5px 11px', borderRadius: 999, color: '#64748b',
            fontSize: 12.5, cursor: 'pointer',
          }}
        >
          {contextOpen ? <ChevronUp size={13} /> : <Plus size={13} />}
          {context ? 'Meeting context added' : 'Add meeting context'}
          {contextOpen && <ChevronDown size={13} style={{ display: 'none' }} />}
        </button>

        <label style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          fontSize: 12.5, color: '#64748b', cursor: 'pointer',
        }}>
          <input
            type="checkbox"
            checked={!!isLongRecording}
            onChange={(e) => onLongRecordingChange?.(e.target.checked)}
            style={{ accentColor: '#0d9488' }}
          />
          Long recording (&gt;15 min) — hierarchical summarisation
        </label>

        {busy && (
          <div style={{ flex: 1, minWidth: 200, display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              flex: 1, height: 6, background: '#e2e8f0', borderRadius: 999, overflow: 'hidden',
            }}>
              <div style={{
                width: `${Math.min(100, Math.max(0, progress || 0))}%`, height: '100%',
                background: 'linear-gradient(90deg,#0d9488,#14b8a6)',
                transition: 'width .3s ease',
              }} />
            </div>
            <div style={{ fontSize: 12, color: '#64748b', whiteSpace: 'nowrap' }}>
              {statusMessage || 'Processing…'}
            </div>
          </div>
        )}
      </div>

      {/* Context textarea (collapsible) */}
      {contextOpen && (
        <div>
          <textarea
            value={context}
            onChange={(e) => onContextChange(e.target.value)}
            placeholder="e.g. Weekly engineering sync. Pay attention to the migration timeline."
            style={{
              width: '100%', minHeight: 76, padding: 10, borderRadius: 10,
              border: '1px solid #e2e8f0', background: '#f8fafc',
              fontSize: 13.5, fontFamily: "'Inter',sans-serif", lineHeight: 1.5,
              outline: 'none', resize: 'vertical', boxSizing: 'border-box',
            }}
          />
          <div style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 10 }}>
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
                background: 'transparent', border: 'none', color: '#64748b',
                fontSize: 12.5, cursor: 'pointer',
                display: 'inline-flex', alignItems: 'center', gap: 5,
              }}
            ><Paperclip size={12} /> Upload .txt as context</button>
          </div>
        </div>
      )}
    </div>
  );
}
