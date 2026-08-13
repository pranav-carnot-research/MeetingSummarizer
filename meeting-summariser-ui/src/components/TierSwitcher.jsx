import React from 'react';
import { Crown, Sparkles, Lock } from 'lucide-react';

export default function TierSwitcher({
  tier,
  onTierChange,
  isSubscribed,
  onOpenPaywall,
  activeLimitsText = '',
}) {
  const isPremium = tier === 'premium' || tier === 'premiere';

  return (
    <div className="app-tier-switcher" style={{
      background: '#faf5ff',
      border: '1px solid #e9d5ff',
      borderRadius: 14,
      padding: '12px 16px',
      marginBottom: 20,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      flexWrap: 'wrap',
      gap: 12,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          background: isPremium ? '#f3e8ff' : '#f0fdf4',
          border: `1px solid ${isPremium ? '#c084fc' : '#bbf7d0'}`,
          borderRadius: 999, padding: '4px 12px',
          fontSize: 12.5, fontWeight: 700,
          color: isPremium ? '#7e22ce' : '#0d9488',
        }}>
          {isPremium ? <Crown size={14} color="#a855f7" /> : <Sparkles size={14} color="#0d9488" />}
          {isPremium ? 'Premium Tier (Restricted)' : 'Free Demo Tier'}
        </div>
        {activeLimitsText && (
          <span style={{ fontSize: 13, color: '#64748b', fontWeight: 500 }}>
            ({activeLimitsText})
          </span>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {/* Tier Switcher Buttons */}
        <div style={{
          display: 'inline-flex', background: '#e9d5ff', borderRadius: 10, padding: 2,
        }}>
          <button
            type="button"
            onClick={() => onTierChange('free')}
            style={{
              padding: '6px 12px', borderRadius: 8, border: 'none',
              background: tier === 'free' ? '#ffffff' : 'transparent',
              color: tier === 'free' ? '#0f172a' : '#64748b',
              fontWeight: 700, fontSize: 12.5, cursor: 'pointer',
              boxShadow: tier === 'free' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
            }}
          >
            Free Demo
          </button>
          <button
            type="button"
            onClick={() => {
              onOpenPaywall('Premium Tier is currently restricted. Payment gateway integration is in progress.');
            }}
            style={{
              padding: '6px 12px', borderRadius: 8, border: 'none',
              background: isPremium ? '#f3e8ff' : 'transparent',
              color: isPremium ? '#6b21a8' : '#64748b',
              fontWeight: 700, fontSize: 12.5, cursor: 'pointer',
              display: 'inline-flex', alignItems: 'center', gap: 4,
              boxShadow: isPremium ? '0 2px 6px rgba(192,132,252,0.3)' : 'none',
            }}
          >
            Premium <Lock size={11} color="#94a3b8" />
          </button>
        </div>

        {/* Subscription Status Badge / Upgrade CTA */}
        <button
          type="button"
          onClick={() => onOpenPaywall('Premium Tier is currently restricted. Payment gateway integration is in progress.')}
          style={{
            background: '#f3e8ff',
            color: '#7e22ce',
            border: '1px solid #c084fc',
            borderRadius: 8,
            padding: '6px 14px', fontWeight: 700, fontSize: 12.5,
            cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6,
            boxShadow: '0 2px 6px rgba(192, 132, 252, 0.25)',
            transition: 'all 0.2s ease',
          }}
        >
          <Crown size={13} color="#d97706" /> Premium Tier 🔒
        </button>
      </div>
    </div>
  );
}


