import React, { useState } from 'react';
import { Card, Label, Button } from '../Card.jsx';
import TierSwitcher from '../TierSwitcher.jsx';
import PaywallModal from '../PaywallModal.jsx';

export default function PasteText({ onChange }) {
  const [text, setText] = useState('');
  const [tier, setTier] = useState('free');
  const [showPaywall, setShowPaywall] = useState(false);
  const [paywallReason, setPaywallReason] = useState('');

  const handleTierChange = (newTier) => {
    if (newTier === 'premium' || newTier === 'premiere') {
      setPaywallReason('Premium Tier is currently restricted. Payment gateway integration is in progress.');
      setShowPaywall(true);
      return;
    }
    setTier(newTier);
  };

  const maxChars = tier === 'premium' ? 50000 : 5000;
  const isOverLimit = text.length > maxChars;

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
        activeLimitsText={tier === 'free' ? 'Max 5,000 chars on Free Demo' : 'Up to 50,000 chars on Premium'}
      />

      <Label>Meeting transcript</Label>
      <textarea
        value={text}
        onChange={(e) => {
          const val = e.target.value;
          setText(val);
          onChange(val);
        }}
        placeholder={`Example:\n\nAlice: Let's kick off the sync…\nBob: The migration is on track.`}
        style={{
          width: '100%', minHeight: 260, padding: 14, borderRadius: 12,
          border: isOverLimit ? '2px solid #ef4444' : '1px solid #cbd5e1',
          background: '#fff', fontSize: 14.5,
          fontFamily: "'Inter', sans-serif", lineHeight: 1.5, outline: 'none', boxSizing: 'border-box',
          resize: 'vertical',
        }}
      />

      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginTop: 8, fontSize: 13,
      }}>
        <span style={{ color: isOverLimit ? '#ef4444' : '#64748b', fontWeight: isOverLimit ? 700 : 400 }}>
          {text.length.toLocaleString()} / {maxChars.toLocaleString()} characters
        </span>

        {isOverLimit && tier === 'free' && (
          <Button
            variant="primary"
            onClick={() => {
              setPaywallReason(`Free Demo limit is 5,000 chars. Your transcript is ${text.length.toLocaleString()} chars.`);
              setShowPaywall(true);
            }}
            style={{ fontSize: 12, padding: '6px 12px' }}
          >
            Premium Tier Restricted 🔒
          </Button>
        )}
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
