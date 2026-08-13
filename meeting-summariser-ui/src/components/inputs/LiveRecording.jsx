import React, { useRef, useState } from 'react';
import { Mic, Square } from 'lucide-react';
import { Card, Label, Button, ProgressBar } from '../Card.jsx';
import { uploadAudio, pollJob } from '../../api/client.js';
import TierSwitcher from '../TierSwitcher.jsx';
import PaywallModal from '../PaywallModal.jsx';

export default function LiveRecording({ languages, onComplete }) {
  const [tier, setTier] = useState('free');
  const [showPaywall, setShowPaywall] = useState(false);
  const [paywallReason, setPaywallReason] = useState('');

  const [language, setLanguage] = useState('auto');
  const [isLong, setIsLong] = useState(false);
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [level, setLevel] = useState(0);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusMsg, setStatusMsg] = useState('');
  const [error, setError] = useState(null);
  const [blob, setBlob] = useState(null);

  const mediaRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const audioCtxRef = useRef(null);
  const analyserRef = useRef(null);
  const rafRef = useRef(null);
  const startTimeRef = useRef(0);

  const handleTierChange = (newTier) => {
    if (newTier === 'premium' || newTier === 'premiere') {
      setPaywallReason('Premium Tier is currently restricted. Payment gateway integration is in progress.');
      setShowPaywall(true);
      return;
    }
    setTier(newTier);
  };

  const maxDurationSec = tier === 'premium' ? 10800 : 300; // 5 mins on Free Demo vs 3 hours on Premium

  const start = async () => {
    setError(null);
    setBlob(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4';
      const rec = new MediaRecorder(stream, { mimeType: mime });
      chunksRef.current = [];
      rec.ondataavailable = (e) => { if (e.data.size) chunksRef.current.push(e.data); };
      rec.onstop = () => {
        const b = new Blob(chunksRef.current, { type: mime });
        setBlob(b);
        stream.getTracks().forEach((t) => t.stop());
      };
      rec.start(1000);
      mediaRef.current = rec;

      // Audio level meter
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const src = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      src.connect(analyser);
      audioCtxRef.current = ctx;
      analyserRef.current = analyser;

      const buf = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteFrequencyData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) sum += buf[i];
        setLevel(Math.min(1, sum / buf.length / 128));
        rafRef.current = requestAnimationFrame(tick);
      };
      tick();

      startTimeRef.current = Date.now();
      setElapsed(0);
      timerRef.current = setInterval(() => {
        const curElapsed = Math.floor((Date.now() - startTimeRef.current) / 1000);
        setElapsed(curElapsed);

        // Auto-stop at tier duration limit
        if (curElapsed >= maxDurationSec) {
          stop();
          if (tier === 'free') {
            setPaywallReason('Free Demo live recording limit (5 minutes) reached.');
            setShowPaywall(true);
          }
        }
      }, 500);
      setRecording(true);
    } catch (e) {
      setError('Microphone access denied or unavailable.');
    }
  };

  const stop = () => {
    if (mediaRef.current) mediaRef.current.stop();
    if (timerRef.current) clearInterval(timerRef.current);
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    if (audioCtxRef.current) audioCtxRef.current.close().catch(() => {});
    setRecording(false);
    setLevel(0);
  };

  const process = async () => {
    if (!blob) return;
    setBusy(true);
    setProgress(0);
    setStatusMsg('Uploading recording…');
    setError(null);
    try {
      const ext = blob.type.includes('mp4') ? 'mp4' : 'webm';
      const file = new File([blob], `recording_${Date.now()}.${ext}`, { type: blob.type });
      const { job_id } = await uploadAudio(file, {
        language,
        isLongRecording: isLong,
        tier,
        isSubscribed,
      });
      const finalStatus = await pollJob(job_id, {
        onUpdate: (s) => {
          setProgress(s.progress || 0);
          setStatusMsg(s.status_message || s.status || 'Processing…');
        },
      });
      const transcriptData = finalStatus.result || finalStatus;
      let transcriptText = '';
      const segs = transcriptData?.transcript;
      if (Array.isArray(segs)) {
        transcriptText = segs
          .map((seg) => `[${seg.start_time_formatted || ''}] Speaker ${seg.speaker || '?'}: ${seg.text || ''}`)
          .join('\n');
      }
      onComplete({
        transcript: transcriptText,
        transcriptData,
        language: transcriptData?.language || (language !== 'auto' ? language : null),
        audioBlob: file,
      });
    } catch (e) {
      setError(e.message || 'Recording processing failed');
    } finally {
      setBusy(false);
    }
  };

  const mins = String(Math.floor(elapsed / 60)).padStart(2, '0');
  const secs = String(elapsed % 60).padStart(2, '0');

  return (
    <Card>
      {/* Tier Switcher */}
      <TierSwitcher
        tier={tier}
        onTierChange={handleTierChange}
        isSubscribed={false}
        onOpenPaywall={(reason) => {
          setPaywallReason(reason);
          setShowPaywall(true);
        }}
        activeLimitsText={tier === 'free' ? 'Max 5 mins on Free Demo' : 'Up to 3 hours on Premium'}
      />

      <div className="app-form-2col" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
        <div>
          <Label>Audio language</Label>
          <select value={language} onChange={(e) => setLanguage(e.target.value)} style={selectStyle}>
            {languages.map((l) => (
              <option key={l.code} value={l.code}>{l.name}</option>
            ))}
          </select>
        </div>
        <div style={{ display: 'flex', alignItems: 'flex-end' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14, color: '#334155' }}>
            <input type="checkbox" checked={isLong} onChange={(e) => setIsLong(e.target.checked)} />
            This will be a long recording (&gt;15 min)
          </label>
        </div>
      </div>

      <div style={{
        background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 14, padding: 24,
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14,
      }}>
        <div style={{
          width: 72, height: 72, borderRadius: '50%',
          background: recording ? '#0d9488' : '#111',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          transform: `scale(${1 + level * 0.25})`, transition: 'transform .12s ease-out, background .2s ease',
          boxShadow: recording ? '0 0 0 8px rgba(13,148,136,0.15)' : '0 6px 16px rgba(17,17,17,0.2)',
        }}>
          <Mic size={30} color="#fff" />
        </div>
        <div style={{ fontFamily: "'Manrope',sans-serif", fontSize: 32, fontWeight: 800, color: '#111' }}>
          {mins}:{secs}
        </div>
        <div style={{ display: 'flex', gap: 12 }}>
          {!recording ? (
            <Button onClick={start} variant="teal" disabled={busy}>
              🎙️ Start Recording
            </Button>
          ) : (
            <Button onClick={stop} variant="primary">
              <Square size={12} style={{ display: 'inline-block', marginRight: 6 }} />
              Stop
            </Button>
          )}
        </div>
      </div>

      {blob && !recording && (
        <div style={{
          marginTop: 16, padding: 14, background: '#f0fdf4',
          border: '1px solid #bbf7d0', borderRadius: 10, color: '#166534',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <span>✅ Recording captured ({(blob.size / 1024).toFixed(0)} KB)</span>
          <Button onClick={process} disabled={busy}>
            {busy ? 'Processing…' : 'Process Recording'}
          </Button>
        </div>
      )}

      {busy && (
        <div style={{ marginTop: 16 }}>
          <ProgressBar value={progress} label={statusMsg} />
        </div>
      )}

      {error && (
        <div style={{
          marginTop: 12, padding: '10px 14px', background: '#fef2f2',
          border: '1px solid #fecaca', color: '#b91c1c', borderRadius: 10, fontSize: 13.5,
        }}>{error}</div>
      )}

      {/* Paywall Modal */}
      <PaywallModal
        isOpen={showPaywall}
        onClose={() => setShowPaywall(false)}
        limitReason={paywallReason}
      />
    </Card>
  );
}

const selectStyle = {
  width: '100%', padding: '10px 12px', borderRadius: 10,
  border: '1px solid #cbd5e1', background: '#fff', fontSize: 14.5, color: '#111', outline: 'none',
};
