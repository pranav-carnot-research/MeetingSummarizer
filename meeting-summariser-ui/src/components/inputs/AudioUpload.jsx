import React, { useRef, useState, useEffect } from 'react';
import { Upload, X, ShieldAlert, Sparkles, Crown, CheckCircle2, Lock, Zap, CreditCard, LockKeyhole, Loader2, ArrowRight } from 'lucide-react';
import { Card, Label, Button, ProgressBar } from '../Card.jsx';
import { uploadAudio, pollJob } from '../../api/client.js';
import PaywallModal from '../PaywallModal.jsx';

const TIER_LIMITS = {
  free: {
    id: 'free',
    name: 'Free Demo',
    maxDurationSec: 300, // 5 minutes
    maxSizeMB: 50,      // 50 MB
    badgeColor: '#0d9488',
    badgeBg: '#f0fdf4',
  },
  premium: {
    id: 'premium',
    name: 'Premium',
    maxDurationSec: 10800, // 3 hours
    maxSizeMB: 500,        // 500 MB
    badgeColor: '#7e22ce',
    badgeBg: '#faf5ff',
  },
  premiere: {
    id: 'premium',
    name: 'Premium',
    maxDurationSec: 10800, // 3 hours
    maxSizeMB: 500,        // 500 MB
    badgeColor: '#7e22ce',
    badgeBg: '#faf5ff',
  },
};

const getAudioDuration = (f) => new Promise((resolve) => {
  if (!f) return resolve(0);
  const audio = new Audio();
  const url = URL.createObjectURL(f);
  audio.onloadedmetadata = () => {
    URL.revokeObjectURL(url);
    resolve(audio.duration || 0);
  };
  audio.onerror = () => {
    URL.revokeObjectURL(url);
    resolve(0);
  };
  audio.src = url;
});

export default function AudioUpload({ languages, onComplete }) {
  const [file, setFile] = useState(null);
  const [tier, setTier] = useState('free'); // 'free' or 'premiere'
  const [isSubscribed, setIsSubscribed] = useState(() => {
    return localStorage.getItem('meeting_summarizer_subscribed') === 'true';
  });
  const [showPaywall, setShowPaywall] = useState(false);
  const [payStep, setPayStep] = useState('overview'); // 'overview' | 'checkout' | 'processing' | 'success'

  // Payment Form State
  const [cardName, setCardName] = useState('Alex Morgan');
  const [cardNumber, setCardNumber] = useState('4242 •••• •••• 4242');
  const [cardExpiry, setCardExpiry] = useState('12/28');
  const [cardCvc, setCardCvc] = useState('888');

  const [language, setLanguage] = useState('auto');
  const [isLong, setIsLong] = useState(false);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusMsg, setStatusMsg] = useState('');
  const [error, setError] = useState(null);
  const [isLimitError, setIsLimitError] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [fileMeta, setFileMeta] = useState(null);
  const inputRef = useRef(null);

  const activeLimit = TIER_LIMITS[tier] || TIER_LIMITS.free;

  useEffect(() => {
    localStorage.setItem('meeting_summarizer_subscribed', isSubscribed ? 'true' : 'false');
  }, [isSubscribed]);

  const validateFile = async (f, currentTier) => {
    if (!f) {
      setFileMeta(null);
      setError(null);
      setIsLimitError(false);
      return true;
    }

    const limits = TIER_LIMITS[currentTier] || TIER_LIMITS.free;
    const sizeMB = f.size / (1024 * 1024);
    const durationSec = await getAudioDuration(f);

    setFileMeta({ durationSec, sizeMB });

    // File Size Check
    if (sizeMB > limits.maxSizeMB) {
      setIsLimitError(true);
      setError(
        `File size (${sizeMB.toFixed(1)} MB) exceeds the ${limits.name} limit of ${limits.maxSizeMB} MB.`
      );
      return false;
    }

    // Duration Check (only if audio metadata was extracted)
    if (durationSec > 0 && durationSec > limits.maxDurationSec) {
      const mins = (durationSec / 60).toFixed(1);
      const maxMins = Math.floor(limits.maxDurationSec / 60);
      setIsLimitError(true);
      setError(
        `Audio duration (${mins} mins) exceeds the ${limits.name} limit of ${maxMins} mins.`
      );
      return false;
    }

    setError(null);
    setIsLimitError(false);
    return true;
  };

  const pickFile = async (f) => {
    setFile(f || null);
    if (f) {
      await validateFile(f, tier);
    } else {
      setError(null);
      setIsLimitError(false);
      setFileMeta(null);
    }
  };

  const openPaywallModal = () => {
    setPayStep('overview');
    setShowPaywall(true);
  };

  const handleTierChange = async (newTier) => {
    if (newTier === 'premiere' && !isSubscribed) {
      openPaywallModal();
      return;
    }

    setTier(newTier);
    if (file) {
      await validateFile(file, newTier);
    }
  };

  const handlePaymentSubmit = (e) => {
    e.preventDefault();
    setPayStep('processing');

    setTimeout(() => {
      setPayStep('success');
      setIsSubscribed(true);
      setTier('premiere');

      setTimeout(async () => {
        setShowPaywall(false);
        setPayStep('overview');
        if (file) {
          await validateFile(file, 'premiere');
        }
      }, 1500);
    }, 1400);
  };

  const handleCancelSubscription = async () => {
    setIsSubscribed(false);
    setTier('free');
    if (file) {
      await validateFile(file, 'free');
    }
  };

  const process = async () => {
    if (!file) return;

    if (tier === 'premiere' && !isSubscribed) {
      openPaywallModal();
      return;
    }

    const isValid = await validateFile(file, tier);
    if (!isValid) return;

    setBusy(true);
    setProgress(0);
    setStatusMsg('Uploading audio…');
    setError(null);

    const t0 = performance.now();
    try {
      const uploadRes = await uploadAudio(file, {
        language,
        isLongRecording: isLong,
        tier,
        isSubscribed,
      });

      const { job_id } = uploadRes || {};
      if (!job_id) {
        throw new Error(`Backend returned no job_id.`);
      }

      const finalStatus = await pollJob(job_id, {
        onUpdate: (s) => {
          setProgress(s.progress || 0);
          setStatusMsg(s.status_message || s.message || s.status || 'Processing…');
        },
      });

      const transcriptData = finalStatus.result || finalStatus;
      const segs = transcriptData?.transcript;

      let transcriptText = '';
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
      const detailMsg = e?.response?.data?.detail;
      if (e?.response?.status === 402) {
        openPaywallModal();
      }
      setError(detailMsg || e?.message || 'Audio processing failed');
    } finally {
      setBusy(false);
    }
  };

  const onDrop = async (e) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) await pickFile(f);
  };

  return (
    <Card>
      {/* Tier Switcher & Subscription Status Bar */}
      <div style={{
        marginBottom: 20,
        padding: '12px 16px',
        background: '#f8fafc',
        borderRadius: 12,
        border: '1px solid #e2e8f0',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 12,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 13, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.05em', color: '#64748b' }}>
            Plan Tier:
          </span>
          <div style={{ display: 'inline-flex', background: '#e2e8f0', padding: 3, borderRadius: 10 }}>
            <button
              type="button"
              onClick={() => handleTierChange('free')}
              style={{
                padding: '6px 14px',
                borderRadius: 8,
                fontSize: 13,
                fontWeight: 600,
                border: 'none',
                cursor: 'pointer',
                transition: 'all .2s ease',
                background: tier === 'free' ? '#fff' : 'transparent',
                color: tier === 'free' ? '#0d9488' : '#64748b',
                boxShadow: tier === 'free' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <Sparkles size={14} /> Free Demo
            </button>
            <button
              type="button"
              onClick={() => openPaywallModal()}
              style={{
                padding: '6px 14px',
                borderRadius: 8,
                fontSize: 13,
                fontWeight: 600,
                border: 'none',
                cursor: 'pointer',
                transition: 'all .2s ease',
                background: tier === 'premium' ? '#f3e8ff' : 'transparent',
                color: tier === 'premium' ? '#6b21a8' : '#64748b',
                boxShadow: tier === 'premium' ? '0 2px 6px rgba(192,132,252,0.3)' : 'none',
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <Crown size={14} color="#94a3b8" /> Premium <Lock size={12} style={{ opacity: 0.7 }} />
            </button>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            type="button"
            onClick={openPaywallModal}
            style={{
              fontSize: 12.5,
              fontWeight: 600,
              padding: '6px 14px',
              borderRadius: 8,
              background: '#f3e8ff',
              color: '#7e22ce',
              border: '1px solid #c084fc',
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              boxShadow: '0 2px 6px rgba(192,132,252,0.25)',
            }}
          >
            <Crown size={13} color="#d97706" /> Premium Tier 🔒
          </button>

          <div style={{
            fontSize: 12,
            fontWeight: 600,
            padding: '4px 10px',
            borderRadius: 8,
            background: activeLimit.badgeBg,
            color: activeLimit.badgeColor,
            border: `1px solid ${activeLimit.badgeColor}33`,
          }}>
            ⚡ Free Demo: Max 5 mins · 50 MB
          </div>
        </div>
      </div>

      <div className="app-form-2col" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
        <div>
          <Label>Audio language</Label>
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            style={selectStyle}
          >
            {languages.map((l) => (
              <option key={l.code} value={l.code}>{l.name}</option>
            ))}
          </select>
        </div>
        <div style={{ display: 'flex', alignItems: 'flex-end' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14, color: '#334155' }}>
            <input type="checkbox" checked={isLong} onChange={(e) => setIsLong(e.target.checked)} />
            This is a long recording (&gt;15 min)
          </label>
        </div>
      </div>

      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        style={{
          border: `2px dashed ${dragOver ? activeLimit.badgeColor : '#cbd5e1'}`,
          background: dragOver ? `${activeLimit.badgeColor}0d` : '#f8fafc',
          borderRadius: 14, padding: '30px 20px', textAlign: 'center', cursor: 'pointer',
          transition: 'border-color .15s ease, background .15s ease',
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".wav,.mp3,.m4a,audio/*"
          hidden
          onChange={(e) => pickFile(e.target.files?.[0])}
        />
        <Upload size={26} color="#64748b" style={{ margin: '0 auto 10px' }} />
        <div style={{ fontWeight: 600, color: '#111' }}>
          {file ? file.name : 'Drop audio here, or click to browse'}
        </div>
        <div style={{ fontSize: 12.5, color: '#94a3b8', marginTop: 4 }}>
          WAV · MP3 · M4A (Max {activeLimit.maxSizeMB} MB &amp; {activeLimit.maxDurationSec / 60} mins on {activeLimit.name})
        </div>

        {fileMeta && (
          <div style={{ fontSize: 12, color: '#64748b', marginTop: 6, fontWeight: 500 }}>
            Detected: {fileMeta.sizeMB.toFixed(1)} MB
            {fileMeta.durationSec > 0 ? ` · ${(fileMeta.durationSec / 60).toFixed(1)} mins` : ''}
          </div>
        )}

        {file && (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); pickFile(null); }}
            style={{
              marginTop: 12, background: 'transparent', border: 'none', cursor: 'pointer',
              color: '#64748b', fontSize: 13, display: 'inline-flex', alignItems: 'center', gap: 4,
            }}
          ><X size={12} /> Remove file</button>
        )}
      </div>

      {busy && (
        <div style={{ marginTop: 16 }}>
          <ProgressBar value={progress} label={statusMsg} />
        </div>
      )}

      {error && (
        <div style={{
          marginTop: 14, padding: '14px 16px', background: '#fef2f2',
          border: '1px solid #fecaca', color: '#b91c1c', borderRadius: 12, fontSize: 13.5,
          display: 'flex', flexDirection: 'column', gap: 10,
        }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
            <ShieldAlert size={18} style={{ flexShrink: 0, marginTop: 1 }} />
            <div>
              <div style={{ fontWeight: 600 }}>Audio Restriction Reached</div>
              <div style={{ marginTop: 2 }}>{error}</div>
            </div>
          </div>

          {isLimitError && !isSubscribed && (
            <div style={{ borderTop: '1px solid #fca5a5', paddingTop: 10, display: 'flex', justifyContent: 'flex-end' }}>
              <button
                type="button"
                onClick={openPaywallModal}
                style={{
                  background: '#7c3aed',
                  color: '#fff',
                  border: 'none',
                  padding: '7px 14px',
                  borderRadius: 8,
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  boxShadow: '0 2px 6px rgba(124,58,237,0.3)',
                }}
              >
                <Crown size={14} /> Subscribe to Premiere to Process File
              </button>
            </div>
          )}
        </div>
      )}

      <div style={{ marginTop: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontSize: 12.5, color: '#64748b' }}>
          Active Tier: <strong style={{ color: activeLimit.badgeColor }}>{activeLimit.name}</strong>
        </div>
        <Button onClick={process} disabled={!file || busy || (!!error && isLimitError)}>
          {busy ? 'Processing…' : 'Process Audio'}
        </Button>
      </div>

      {/* Interactive Payment Checkout Modal */}
      <PaywallModal
        isOpen={showPaywall}
        onClose={() => setShowPaywall(false)}
        limitReason={error}
      />
    </Card>
  );
}

const selectStyle = {
  width: '100%', padding: '10px 12px', borderRadius: 10,
  border: '1px solid #cbd5e1', background: '#fff', fontSize: 14.5, color: '#111',
  outline: 'none',
};

const inputStyle = {
  width: '100%', padding: '10px 12px', borderRadius: 10,
  border: '1px solid #cbd5e1', background: '#fff', fontSize: 14, color: '#111',
  outline: 'none',
  boxSizing: 'border-block',
};

const featureRowStyle = {
  display: 'flex',
  alignItems: 'flex-start',
  gap: 10,
  fontSize: 13.5,
};
