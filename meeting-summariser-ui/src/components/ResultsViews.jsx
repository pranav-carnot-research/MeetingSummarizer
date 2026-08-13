import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Play, Pause, Download, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { Card } from './Card.jsx';

function fmtTime(secs) {
  if (secs == null || Number.isNaN(secs)) return '--:--';
  const m = Math.floor(secs / 60);
  const s = Math.floor(secs % 60);
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function confColor(c) {
  if (c == null) return { fg: '#94a3b8', bg: 'transparent' };
  if (c >= 90) return { fg: '#166534', bg: 'rgba(76,175,80,0.14)' };
  if (c >= 70) return { fg: '#9a5b00', bg: 'rgba(255,152,0,0.16)' };
  return { fg: '#b91c1c', bg: 'rgba(244,67,54,0.16)' };
}

// ─────────────────────────────────────────────────────────────
// Standalone audio view — the raw recording, big & centred, with
// download + file metadata.
// ─────────────────────────────────────────────────────────────
export function AudioPlayerView({ audioBlob, audioUrl }) {
  const audioRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    const onTime = () => setTime(el.currentTime);
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
  }, [audioUrl]);

  if (!audioUrl) {
    return (
      <Card>
        <div style={emptyStyle}>No audio available — this session used a text transcript.</div>
      </Card>
    );
  }

  const toggle = () => {
    const el = audioRef.current; if (!el) return;
    if (el.paused) el.play().catch(() => {}); else el.pause();
  };

  const download = () => {
    if (!audioBlob) return;
    const url = URL.createObjectURL(audioBlob);
    const a = document.createElement('a');
    a.href = url;
    a.download = audioBlob.name || 'recording';
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <Card>
      {audioBlob && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
          <button onClick={download} style={ghostBtn}>
            <Download size={14} style={{ marginRight: 6 }} /> Download
          </button>
        </div>
      )}

      {/* Player card — white surface with soft elevation and a subtle
          teal wash at the leading edge. On the app's light palette but
          with enough visual weight not to disappear; the teal-glowing
          play button carries the brand accent. */}
      <div style={{
        background: 'linear-gradient(90deg, rgba(13,148,136,0.06) 0%, #ffffff 45%, #ffffff 100%)',
        border: '1px solid #e2e8f0',
        borderRadius: 16,
        padding: '22px 24px',
        display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap',
        color: '#0f172a',
        boxShadow: '0 4px 16px rgba(15,23,42,0.06)',
      }}>
        <button
          onClick={toggle}
          aria-label={playing ? 'Pause' : 'Play'}
          style={{
            width: 60, height: 60, borderRadius: '50%', border: 'none', cursor: 'pointer',
            background: '#0d9488', color: '#ffffff',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
            boxShadow: '0 8px 22px rgba(13,148,136,0.32)',
            transition: 'transform .18s ease, box-shadow .18s ease',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.transform = 'scale(1.04)'; }}
          onMouseLeave={(e) => { e.currentTarget.style.transform = 'scale(1)'; }}
        >{playing ? <Pause size={22} /> : <Play size={22} style={{ marginLeft: 2 }} />}</button>

        <div style={{ flex: 1, minWidth: 220 }}>
          <div style={{
            fontFamily: 'ui-monospace, monospace', fontSize: 13,
            color: '#475569', marginBottom: 10, fontWeight: 600,
            letterSpacing: '.02em',
          }}>
            {fmtTime(time)} <span style={{ color: '#94a3b8', fontWeight: 500 }}>/ {fmtTime(duration)}</span>
          </div>
          <input
            type="range" min="0" max={duration || 0} step="0.1" value={time}
            onChange={(e) => { const el = audioRef.current; if (el) el.currentTime = parseFloat(e.target.value); }}
            style={{ width: '100%', accentColor: '#0d9488', cursor: 'pointer' }}
          />
        </div>
      </div>

      {audioBlob && (
        <div style={{
          marginTop: 14, display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))',
          gap: 10, fontSize: 13, color: '#334155',
        }}>
          <Meta label="File" value={audioBlob.name || '—'} />
          <Meta label="Size" value={`${(audioBlob.size / (1024 * 1024)).toFixed(2)} MB`} />
          <Meta label="Type" value={audioBlob.type || 'audio'} />
          <Meta label="Duration" value={fmtTime(duration)} />
        </div>
      )}

      <audio ref={audioRef} src={audioUrl} preload="metadata" style={{ display: 'none' }} />
    </Card>
  );
}

function Meta({ label, value }) {
  return (
    <div style={{
      background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 10,
      padding: '10px 12px',
    }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', letterSpacing: '.08em', textTransform: 'uppercase' }}>{label}</div>
      <div style={{ marginTop: 3, fontSize: 13.5, color: '#111', wordBreak: 'break-word' }}>{value}</div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Confidence view — headline metric, distribution bar,
// and a "needs review" list of low-confidence segments so the user
// can jump straight to where the transcript is unreliable.
// ─────────────────────────────────────────────────────────────
export function ConfidenceView({ transcriptData, onOpenTranscript }) {
  const metrics = transcriptData?.confidence_metrics;
  const segments = transcriptData?.transcript || [];

  const { high, med, low, total } = useMemo(() => {
    let h = 0, m = 0, l = 0, t = 0;
    segments.forEach((s) => {
      const c = s.confidence;
      if (c == null) return;
      t += 1;
      if (c >= 90) h += 1;
      else if (c >= 70) m += 1;
      else l += 1;
    });
    return { high: h, med: m, low: l, total: t };
  }, [segments]);

  const pct = (n) => (total ? Math.round((n / total) * 100) : 0);

  const lowSegs = useMemo(
    () => segments
      .map((s, i) => ({ ...s, _idx: i }))
      .filter((s) => s.confidence != null && s.confidence < 70)
      .sort((a, b) => a.confidence - b.confidence),
    [segments],
  );

  if (!segments.length) {
    return (
      <Card>
        <div style={emptyStyle}>Confidence scores appear only for audio transcribed by Whisper.</div>
      </Card>
    );
  }

  return (
    <Card>
      {/* Headline metrics */}
      {metrics && metrics.average != null && (
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))',
          gap: 12, marginBottom: 20,
        }}>
          <BigStat label="Average" value={`${metrics.average}%`} tone={metrics.average >= 90 ? 'good' : metrics.average >= 70 ? 'warn' : 'bad'} />
          <BigStat label="Minimum" value={`${metrics.min}%`} />
          <BigStat label="Maximum" value={`${metrics.max}%`} />
          <BigStat
            label="Low confidence"
            value={`${metrics.low_confidence_percentage ?? pct(low)}%`}
            tone={(metrics.low_confidence_percentage ?? pct(low)) > 15 ? 'bad' : 'good'}
          />
        </div>
      )}

      {/* Distribution bar */}
      {total > 0 && (
        <div style={{ marginBottom: 20 }}>
          <div style={{
            fontSize: 12, color: '#64748b', marginBottom: 6,
            display: 'flex', justifyContent: 'space-between',
          }}>
            <span>Segment distribution ({total} segments)</span>
            <span>🟢 {high} · 🟡 {med} · 🔴 {low}</span>
          </div>
          <div style={{
            display: 'flex', height: 12, borderRadius: 999, overflow: 'hidden',
            border: '1px solid #e2e8f0',
          }}>
            <div style={{ width: `${pct(high)}%`, background: '#4ade80' }} title={`High: ${high}`} />
            <div style={{ width: `${pct(med)}%`, background: '#fbbf24' }} title={`Medium: ${med}`} />
            <div style={{ width: `${pct(low)}%`, background: '#f87171' }} title={`Low: ${low}`} />
          </div>
        </div>
      )}

      {/* Needs-review list */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10,
        fontSize: 13, fontWeight: 700, color: '#0f172a',
      }}>
        {lowSegs.length ? <AlertTriangle size={15} color="#b91c1c" /> : <CheckCircle2 size={15} color="#166534" />}
        {lowSegs.length ? `${lowSegs.length} segments below 70% — worth reviewing` : 'No low-confidence segments — you\'re clean.'}
      </div>

      {lowSegs.length > 0 && (
        <div style={{
          maxHeight: 380, overflowY: 'auto',
          background: '#f8fafc', border: '1px solid #e2e8f0',
          borderRadius: 12, padding: 8,
        }}>
          {lowSegs.map((s) => {
            const { fg, bg } = confColor(s.confidence);
            return (
              <div key={s._idx}
                onClick={() => onOpenTranscript?.(s._idx)}
                style={{
                  padding: '10px 12px', borderRadius: 8, marginBottom: 4,
                  background: bg, cursor: 'pointer',
                }}
              >
                <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', fontSize: 12.5, color: '#64748b', marginBottom: 3 }}>
                  <span style={{ fontFamily: 'ui-monospace, monospace' }}>
                    [{s.start_time_formatted || fmtTime(s.start_time)}]
                  </span>
                  <span>Speaker {s.speaker ?? '?'}</span>
                  <span style={{ marginLeft: 'auto', color: fg, fontWeight: 700 }}>
                    {Math.round(s.confidence)}%
                  </span>
                </div>
                <div style={{ fontSize: 13.5, color: '#2a2823', lineHeight: 1.55 }}>{s.text}</div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}

function BigStat({ label, value, tone }) {
  const bg = tone === 'good' ? 'rgba(76,175,80,0.10)'
    : tone === 'warn' ? 'rgba(255,152,0,0.10)'
    : tone === 'bad' ? 'rgba(244,67,54,0.10)'
    : '#f8fafc';
  const fg = tone === 'good' ? '#166534'
    : tone === 'warn' ? '#9a5b00'
    : tone === 'bad' ? '#b91c1c'
    : '#0f172a';
  return (
    <div style={{
      background: bg, border: '1px solid #e2e8f0', borderRadius: 12,
      padding: '14px 16px',
    }}>
      <div style={{ fontSize: 11, fontWeight: 800, color: '#94a3b8', letterSpacing: '.1em', textTransform: 'uppercase' }}>{label}</div>
      <div style={{
        marginTop: 4, fontFamily: "'Manrope',sans-serif", fontWeight: 800,
        fontSize: 26, color: fg, letterSpacing: '-0.02em',
      }}>{value}</div>
    </div>
  );
}

const ghostBtn = {
  display: 'inline-flex', alignItems: 'center', background: 'transparent',
  border: '1px solid #e2e8f0', color: '#111', padding: '7px 13px', borderRadius: 9,
  fontSize: 13, fontWeight: 600, cursor: 'pointer',
};
const emptyStyle = { color: '#94a3b8', fontStyle: 'italic', fontSize: 14, padding: '10px 0' };
