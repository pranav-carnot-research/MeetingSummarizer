import React, { useRef, useState } from 'react';
import { FileUp, X } from 'lucide-react';
import { Card, Button } from '../Card.jsx';
import { uploadText } from '../../api/client.js';
import TierSwitcher from '../TierSwitcher.jsx';
import PaywallModal from '../PaywallModal.jsx';

export default function UploadText({ onLoaded }) {
  const [file, setFile] = useState(null);
  const [tier, setTier] = useState('free');
  const [showPaywall, setShowPaywall] = useState(false);
  const [paywallReason, setPaywallReason] = useState('');

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [participants, setParticipants] = useState([]);
  const inputRef = useRef(null);

  const handleTierChange = (newTier) => {
    if (newTier === 'premium' || newTier === 'premiere') {
      setPaywallReason('Premium Tier is currently restricted. Payment gateway integration is in progress.');
      setShowPaywall(true);
      return;
    }
    setTier(newTier);
  };

  const maxMB = tier === 'premium' ? 10 : 1;

  const pick = (f) => {
    setError(null);
    if (!f) {
      setFile(null);
      return;
    }

    const fileSizeMB = f.size / (1024 * 1024);
    if (fileSizeMB > maxMB) {
      if (tier === 'free') {
        setPaywallReason(`File size is ${fileSizeMB.toFixed(1)} MB. Free Demo limit is 1 MB.`);
        setShowPaywall(true);
      } else {
        setError(`File size (${fileSizeMB.toFixed(1)} MB) exceeds Premium limit of 10 MB.`);
      }
      setFile(null);
      return;
    }

    setFile(f);
  };

  const load = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const res = await uploadText(file);
      setParticipants(res.participants || []);
      onLoaded({ transcript: res.transcript || '', participants: res.participants || [] });
    } catch (e) {
      setError(e.message || 'Upload failed');
    } finally {
      setBusy(false);
    }
  };

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
        activeLimitsText={tier === 'free' ? 'Max 1 MB .txt file on Free Demo' : 'Up to 10 MB on Premium'}
      />

      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); pick(e.dataTransfer.files?.[0]); }}
        onClick={() => inputRef.current?.click()}
        style={{
          border: '2px dashed #cbd5e1', background: '#f8fafc', borderRadius: 14,
          padding: '30px 20px', textAlign: 'center', cursor: 'pointer',
        }}
      >
        <input ref={inputRef} type="file" accept=".txt" hidden onChange={(e) => pick(e.target.files?.[0])} />
        <FileUp size={26} color="#64748b" style={{ margin: '0 auto 10px' }} />
        <div style={{ fontWeight: 600, color: '#111' }}>
          {file ? file.name : 'Drop a .txt transcript file, or click to browse'}
        </div>
        {file && (
          <button
            onClick={(e) => { e.stopPropagation(); pick(null); setParticipants([]); }}
            style={{ marginTop: 10, background: 'transparent', border: 'none', color: '#64748b', fontSize: 13, cursor: 'pointer' }}
          ><X size={12} /> Remove</button>
        )}
      </div>

      {participants.length > 0 && (
        <div style={{ marginTop: 12, fontSize: 13.5, color: '#166534', background: '#f0fdf4', border: '1px solid #bbf7d0', padding: '10px 14px', borderRadius: 10 }}>
          ✅ Detected participants: {participants.join(', ')}
        </div>
      )}

      {error && (
        <div style={{ marginTop: 12, padding: '10px 14px', background: '#fef2f2', border: '1px solid #fecaca', color: '#b91c1c', borderRadius: 10, fontSize: 13.5 }}>{error}</div>
      )}

      <div style={{ marginTop: 20, display: 'flex', justifyContent: 'flex-end' }}>
        <Button onClick={load} disabled={!file || busy}>
          {busy ? 'Loading…' : 'Load File'}
        </Button>
      </div>

      {/* Paywall Modal */}
      <PaywallModal
        isOpen={showPaywall}
        onClose={() => setShowPaywall(false)}
        limitReason={paywallReason}
      />
    </Card>
  );
}
