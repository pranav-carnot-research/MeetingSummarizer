import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Play, Pause, Pencil, Check, X, ChevronDown } from 'lucide-react';
import { Card } from './Card.jsx';

// ── Confidence → colour helpers (mirrors backend/app.py) ────────────────
function confColor(c) {
  if (c == null) return { fg: '#94a3b8', bg: 'transparent' };
  if (c >= 90) return { fg: '#166534', bg: 'rgba(76,175,80,0.14)' };
  if (c >= 70) return { fg: '#9a5b00', bg: 'rgba(255,152,0,0.16)' };
  return { fg: '#b91c1c', bg: 'rgba(244,67,54,0.16)' };
}
function confDot(c) {
  if (c == null) return '⚫';
  if (c >= 90) return '🟢';
  if (c >= 70) return '🟡';
  return '🔴';
}
function fmtTime(secs) {
  if (secs == null || Number.isNaN(secs)) return '--:--';
  const m = Math.floor(secs / 60);
  const s = Math.floor(secs % 60);
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}
function parseFormatted(str) {
  // Accepts "mm:ss" or "hh:mm:ss" → seconds. Returns null on failure.
  if (!str || typeof str !== 'string') return null;
  const parts = str.split(':').map((p) => parseInt(p, 10));
  if (parts.some(Number.isNaN)) return null;
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  if (parts.length === 1) return parts[0];
  return null;
}

// Try hard to get a numeric start time from whatever the backend sent
function segStartSecs(seg) {
  if (typeof seg?.start_time === 'number') return seg.start_time;
  if (typeof seg?.start === 'number') return seg.start;
  const p = parseFormatted(seg?.start_time_formatted || seg?.start_formatted);
  return p != null ? p : null;
}
function segEndSecs(seg) {
  if (typeof seg?.end_time === 'number') return seg.end_time;
  if (typeof seg?.end === 'number') return seg.end;
  const p = parseFormatted(seg?.end_time_formatted || seg?.end_formatted);
  return p != null ? p : null;
}

// Extract word-level entries from a segment's nested `segments[].words`
function segWords(seg) {
  const inner = seg?.segments;
  const out = [];
  if (Array.isArray(inner)) {
    inner.forEach((sub) => {
      if (Array.isArray(sub?.words)) out.push(...sub.words);
    });
  }
  if (!out.length && Array.isArray(seg?.words)) return seg.words;
  return out;
}

// ── Rebuild flat "[time] Speaker N: text" transcript from edited segments
function rebuildFlatTranscript(segments) {
  return segments
    .map((s) => {
      const t = s.start_time_formatted || fmtTime(segStartSecs(s));
      return `[${t}] Speaker ${s.speaker ?? '?'}: ${s.text || ''}`;
    })
    .join('\n');
}

export default function TranscriptPreview({
  transcriptData,   // { transcript: [...], raw_transcription?, confidence_metrics?, language? }
  audioSrc,         // blob URL for playback (optional)
  onTranscriptChange, // (flatText, updatedData) => void
}) {
  const [view, setView] = useState('diarized');
  const [segments, setSegments] = useState(() => transcriptData?.transcript || []);
  const rawSegments = transcriptData?.raw_transcription || [];
  const metrics = transcriptData?.confidence_metrics;
  const [editing, setEditing] = useState(false);
  const [audioTime, setAudioTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const audioRef = useRef(null);
  const listRef = useRef(null);

  // Reset local state when backend hands us a new transcript
  useEffect(() => {
    setSegments(transcriptData?.transcript || []);
  }, [transcriptData]);

  // Distinct speakers → name overrides live locally
  const [speakerNames, setSpeakerNames] = useState({});
  const distinctSpeakers = useMemo(() => {
    const s = new Set();
    segments.forEach((seg) => s.add(String(seg.speaker ?? '?')));
    return [...s];
  }, [segments]);

  // Format a raw diarization key like "SPEAKER_00" as "Speaker 00" so the
  // rendered label doesn't double up ("Speaker SPEAKER_00"). If the user has
  // typed a friendly name for this speaker, prefer that verbatim.
  const displaySpeaker = (raw) => {
    if (speakerNames[String(raw)]) return speakerNames[String(raw)];
    const s = String(raw ?? '?');
    const m = s.match(/^speaker[_\s-]*(.+)$/i);
    return m ? `Speaker ${m[1]}` : `Speaker ${s}`;
  };
  const speakerShortLabel = (raw) => {
    const s = String(raw ?? '?');
    const m = s.match(/^speaker[_\s-]*(.+)$/i);
    return m ? `Speaker ${m[1]}` : `Speaker ${s}`;
  };

  // ── Audio playback ─────────────────────────────────────────
  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    const onTime = () => setAudioTime(el.currentTime);
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onLoaded = () => setDuration(el.duration || 0);
    el.addEventListener('timeupdate', onTime);
    el.addEventListener('play', onPlay);
    el.addEventListener('pause', onPause);
    el.addEventListener('loadedmetadata', onLoaded);
    return () => {
      el.removeEventListener('timeupdate', onTime);
      el.removeEventListener('play', onPlay);
      el.removeEventListener('pause', onPause);
      el.removeEventListener('loadedmetadata', onLoaded);
    };
  }, [audioSrc]);

  const seekTo = (secs) => {
    const el = audioRef.current;
    if (!el || secs == null) return;
    el.currentTime = secs;
    if (el.paused) el.play().catch(() => {});
  };

  const togglePlay = () => {
    const el = audioRef.current;
    if (!el) return;
    if (el.paused) el.play().catch(() => {});
    else el.pause();
  };

  // Which segment is currently active
  const activeIdx = useMemo(() => {
    for (let i = 0; i < segments.length; i++) {
      const s = segStartSecs(segments[i]);
      const e = segEndSecs(segments[i]);
      if (s != null && e != null && audioTime >= s && audioTime < e) return i;
    }
    return -1;
  }, [audioTime, segments]);

  // Auto-scroll to active segment
  useEffect(() => {
    if (activeIdx < 0 || !listRef.current || editing) return;
    const el = listRef.current.querySelector(`[data-seg="${activeIdx}"]`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [activeIdx, editing]);

  // ── Editing handlers ───────────────────────────────────────
  const editSegText = (idx, text) => {
    const next = segments.map((s, i) => (i === idx ? { ...s, text } : s));
    setSegments(next);
  };

  const commitEdits = () => {
    // Bake speaker renames into each segment's `speaker` field so downstream
    // consumers (summary, follow-up emails, flat transcript) see the friendly
    // name instead of the raw diarization key. Strip a leading "Speaker "
    // prefix if the user typed one so we don't produce "Speaker Speaker Alice".
    const named = segments.map((s) => {
      const rename = speakerNames[String(s.speaker ?? '?')];
      if (!rename) return s;
      const cleaned = rename.replace(/^Speaker\s*/i, '').trim();
      return cleaned ? { ...s, speaker: cleaned } : s;
    });
    setSegments(named);
    onTranscriptChange?.(rebuildFlatTranscript(named), {
      ...transcriptData,
      transcript: named,
    });
    // Clear the local rename map — the names are now part of the segments,
    // so the "Rename speakers" inputs should start fresh on next edit.
    setSpeakerNames({});
    setEditing(false);
  };

  const cancelEdits = () => {
    setSegments(transcriptData?.transcript || []);
    setSpeakerNames({});
    setEditing(false);
  };

  const currentList = view === 'diarized' ? segments : rawSegments;

  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, flexWrap: 'wrap', gap: 12 }}>
        <div style={{ fontSize: 13, color: '#64748b' }}>
          Colours show Whisper confidence — hover any word for its exact score.
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {!editing ? (
            <button onClick={() => setEditing(true)} style={btnGhost}>
              <Pencil size={14} style={{ marginRight: 6 }} /> Edit
            </button>
          ) : (
            <>
              <button onClick={cancelEdits} style={btnGhost}>
                <X size={14} style={{ marginRight: 6 }} /> Cancel
              </button>
              <button onClick={commitEdits} style={btnTeal}>
                <Check size={14} style={{ marginRight: 6 }} /> Save edits
              </button>
            </>
          )}
        </div>
      </div>

      {/* Legend + metrics */}
      <div className="app-transcript-legend" style={{ display: 'flex', flexWrap: 'wrap', gap: 14, fontSize: 12.5, color: '#64748b', marginBottom: 10 }}>
        <span>🟢 High (≥90%)</span>
        <span>🟡 Medium (70–89%)</span>
        <span>🔴 Low (&lt;70%)</span>
        <span style={{ color: '#94a3b8', fontStyle: 'italic', marginLeft: 'auto' }}>💡 Hover a word to see its confidence</span>
      </div>
      {metrics && metrics.average != null && (
        <div style={{
          display: 'flex', gap: 20, background: '#f8fafc', border: '1px solid #e2e8f0',
          borderRadius: 10, padding: '8px 14px', fontSize: 13, color: '#334155', marginBottom: 12,
        }}>
          <span>Avg: <strong style={{ color: confColor(metrics.average).fg }}>{metrics.average}%</strong></span>
          <span>Min: <strong>{metrics.min}%</strong></span>
          <span>Max: <strong>{metrics.max}%</strong></span>
          {metrics.low_confidence_percentage != null && (
            <span>Low-conf: <strong>{metrics.low_confidence_percentage}%</strong></span>
          )}
        </div>
      )}

      {/* Audio player */}
      {audioSrc && (
        <div className="app-audio-player" style={{
          display: 'flex', alignItems: 'center', gap: 12,
          background: '#f8fafc', border: '1px solid #e2e8f0',
          color: '#111', padding: '10px 14px', borderRadius: 12, marginBottom: 12,
        }}>
          <button onClick={togglePlay} style={{
            width: 38, height: 38, borderRadius: '50%', border: 'none', cursor: 'pointer',
            background: '#0d9488', color: '#0f172a', display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 4px 12px rgba(13,148,136,0.28)',
          }}>{playing ? <Pause size={16} /> : <Play size={16} />}</button>
          <div style={{ fontFamily: 'ui-monospace, monospace', fontSize: 13, color: '#334155' }}>
            {fmtTime(audioTime)} / {fmtTime(duration)}
          </div>
          <input
            type="range"
            min="0"
            max={duration || 0}
            step="0.1"
            value={audioTime}
            onChange={(e) => { const el = audioRef.current; if (el) el.currentTime = parseFloat(e.target.value); }}
            style={{ flex: 1, accentColor: '#0d9488' }}
          />
          <audio ref={audioRef} src={audioSrc} preload="metadata" style={{ display: 'none' }} />
        </div>
      )}

      {/* Speaker rename bar (only visible in edit mode) */}
      {editing && distinctSpeakers.length > 0 && (
        <div style={{
          background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 10,
          padding: '12px 14px', marginBottom: 10, fontSize: 13,
        }}>
          <div style={{
            fontWeight: 700, marginBottom: 10, color: '#0f172a',
            fontSize: 12.5, letterSpacing: '.06em', textTransform: 'uppercase',
          }}>Rename speakers</div>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
            gap: 10,
          }}>
            {distinctSpeakers.map((sp) => (
              <label key={sp} className="app-rename-row" style={{
                display: 'grid', gridTemplateColumns: 'max-content 1fr',
                alignItems: 'center', gap: 10,
              }}>
                <span style={{
                  fontSize: 12.5, color: '#64748b', whiteSpace: 'nowrap',
                  fontFamily: 'ui-monospace, SFMono-Regular, monospace',
                }}>{speakerShortLabel(sp)}</span>
                <input
                  value={speakerNames[sp] || ''}
                  placeholder="e.g., Alice"
                  onChange={(e) => setSpeakerNames((s) => ({ ...s, [sp]: e.target.value }))}
                  style={{
                    minWidth: 0, width: '100%',
                    padding: '6px 10px', border: '1px solid #cbd5e1', borderRadius: 6,
                    fontSize: 13, outline: 'none', background: '#ffffff',
                    boxSizing: 'border-box',
                  }}
                />
              </label>
            ))}
          </div>
        </div>
      )}

      {/* View toggle: diarized ↔ raw (only if raw exists) */}
      {rawSegments.length > 0 && (
        <div style={{ display: 'flex', gap: 6, background: '#f1f5f9', padding: 5, borderRadius: 10, marginBottom: 10, width: 'fit-content' }}>
          {[
            { id: 'diarized', label: '🔊 Speaker-diarized' },
            { id: 'raw', label: '📝 Raw Whisper' },
          ].map((t) => (
            <button
              key={t.id}
              onClick={() => setView(t.id)}
              style={{
                padding: '6px 14px', borderRadius: 7, border: 'none', cursor: 'pointer',
                fontSize: 13, fontWeight: 600,
                background: view === t.id ? '#fff' : 'transparent',
                color: view === t.id ? '#111' : '#64748b',
                boxShadow: view === t.id ? '0 1px 3px rgba(17,17,17,0.06)' : 'none',
              }}
            >{t.label}</button>
          ))}
        </div>
      )}

      {/* Segments list */}
      <div
        ref={listRef}
        style={{
          maxHeight: 460, overflowY: 'auto',
          background: '#f8fafc', border: '1px solid #e2e8f0',
          borderRadius: 12, padding: 12,
          fontSize: 13.5, lineHeight: 1.7, color: '#2a2823',
        }}
      >
        {currentList.length === 0 && (
          <div style={{ color: '#94a3b8', textAlign: 'center', padding: 20 }}>No segments to display.</div>
        )}
        {currentList.map((seg, idx) => {
          const isRaw = view === 'raw';
          const ts = seg.start_time_formatted || seg.start_formatted || fmtTime(segStartSecs(seg));
          const seg_conf = seg.confidence;
          const dot = confDot(seg_conf);
          const words = segWords(seg);
          const isActive = !isRaw && idx === activeIdx;
          const start = segStartSecs(seg);
          const speakerDisplay = isRaw ? '' : displaySpeaker(seg.speaker);

          return (
            <div
              key={idx}
              data-seg={idx}
              onClick={() => start != null && seekTo(start)}
              style={{
                padding: '8px 10px', borderRadius: 8, marginBottom: 4,
                cursor: start != null ? 'pointer' : 'default',
                background: isActive ? 'rgba(13,148,136,0.14)' : 'transparent',
                borderLeft: isActive ? '3px solid #0d9488' : '3px solid transparent',
                transition: 'background .15s ease',
              }}
            >
              <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap' }}>
                <span>{dot}</span>
                <span style={{ color: '#94a3b8', fontSize: 12, fontFamily: 'ui-monospace, monospace' }}>[{ts}]</span>
                {!isRaw && (
                  <strong style={{ color: '#0f766e', fontSize: 13, marginRight: 4 }}>
                    {speakerDisplay}:
                  </strong>
                )}

                {editing && !isRaw ? (
                  <textarea
                    value={seg.text || ''}
                    onChange={(e) => editSegText(idx, e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                    style={{
                      flex: 1, minWidth: 240, minHeight: 46, padding: 8, borderRadius: 6,
                      border: '1px solid #cbd5e1', background: '#ffffff', color: '#111',
                      fontFamily: "'Inter', sans-serif", fontSize: 13.5, lineHeight: 1.5,
                      resize: 'vertical', outline: 'none',
                    }}
                  />
                ) : words.length > 0 ? (
                  <span style={{ flex: 1, color: '#2a2823' }}>
                    {words.map((w, wi) => {
                      const c = w.confidence;
                      const { fg, bg } = confColor(c);
                      return (
                        <span
                          key={wi}
                          title={c != null ? `${c.toFixed ? c.toFixed(1) : c}%` : ''}
                          style={{
                            color: fg, background: bg, padding: '0 2px',
                            borderRadius: 3, marginRight: 2,
                          }}
                        >{w.word}</span>
                      );
                    })}
                  </span>
                ) : (
                  <span style={{ flex: 1, color: confColor(seg_conf).fg || '#2a2823' }}>{seg.text}</span>
                )}

                {seg_conf != null && (
                  <span style={{ color: '#94a3b8', fontSize: 11 }}>({Math.round(seg_conf)}%)</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {editing && (
        <div style={{
          marginTop: 10, padding: '8px 12px', background: '#f0fdf4', border: '1px solid #bbf7d0',
          borderRadius: 8, fontSize: 12.5, color: '#166534', display: 'flex', alignItems: 'center', gap: 6,
        }}>
          <ChevronDown size={14} /> Editing mode — click <strong>Save edits</strong> above to apply changes to the summary input.
        </div>
      )}
    </Card>
  );
}

const btnGhost = {
  display: 'inline-flex', alignItems: 'center', background: 'transparent',
  border: '1px solid #e2e8f0', color: '#111', padding: '7px 13px', borderRadius: 9,
  fontSize: 13, fontWeight: 600, cursor: 'pointer',
};
const btnTeal = {
  display: 'inline-flex', alignItems: 'center', background: '#0d9488',
  border: 'none', color: '#111', padding: '7px 13px', borderRadius: 9,
  fontSize: 13, fontWeight: 700, cursor: 'pointer',
};
