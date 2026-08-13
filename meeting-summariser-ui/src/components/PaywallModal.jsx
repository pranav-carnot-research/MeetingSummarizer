import React from 'react';
import { Crown, Lock, AlertCircle, X } from 'lucide-react';

export default function PaywallModal({ isOpen, onClose, limitReason = '' }) {
  if (!isOpen) return null;

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: 'rgba(15, 23, 42, 0.75)',
      backdropFilter: 'blur(6px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 16,
    }}>
      <div style={{
        background: '#ffffff',
        borderRadius: 20,
        maxWidth: 480,
        width: '100%',
        boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
        border: '1px solid #e2e8f0',
        overflow: 'hidden',
        animation: 'modalSlideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
        position: 'relative',
      }}>
        {/* Close Button */}
        <button
          onClick={onClose}
          style={{
            position: 'absolute', top: 16, right: 16,
            background: 'rgba(241, 245, 249, 0.8)', border: 'none',
            borderRadius: '50%', width: 32, height: 32,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer', zIndex: 10, color: '#64748b',
          }}
        >
          <X size={16} />
        </button>

        {/* Modal Header */}
        <div style={{
          background: 'linear-gradient(135deg, #faf5ff, #f3e8ff, #e9d5ff)',
          padding: '24px 24px 20px',
          color: '#4c1d95',
          borderBottom: '1px solid #e9d5ff',
        }}>
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            background: '#ffffff',
            border: '1px solid #c084fc',
            padding: '4px 12px', borderRadius: 999,
            fontSize: 12, fontWeight: 700, letterSpacing: '0.04em',
            textTransform: 'uppercase', marginBottom: 10,
            color: '#7e22ce',
          }}>
            <Crown size={14} color="#d97706" /> Premium Tier Restricted
          </div>
          <h2 style={{ fontSize: 22, fontWeight: 800, margin: '0 0 6px', color: '#3b0764' }}>
            {limitReason ? 'Premium Tier Required' : 'Premium Tier Coming Soon'}
          </h2>
          <p style={{ fontSize: 13.5, color: '#6b21a8', margin: 0, lineHeight: 1.4, fontWeight: 500 }}>
            Payment gateway integration is currently in progress. Audio ingestion is strictly limited to Free Demo quotas.
          </p>
        </div>

        {/* Modal Body */}
        <div style={{ padding: '24px 24px 22px' }}>
          <div style={{
            background: '#fff1f2',
            border: '1px solid #fecdd3',
            borderRadius: 14,
            padding: '16px 18px',
            marginBottom: 20,
            display: 'flex',
            alignItems: 'flex-start',
            gap: 12,
          }}>
            <AlertCircle size={20} color="#e11d48" style={{ flexShrink: 0, marginTop: 2 }} />
            <div>
              <div style={{ fontSize: 14, fontWeight: 700, color: '#9f1239', marginBottom: 4 }}>
                Audio Uploads Restricted
              </div>
              <div style={{ fontSize: 13, color: '#be123c', lineHeight: 1.5 }}>
                {limitReason || 'You cannot upload audio under Premium limits yet because payment gateway integration is pending.'}
                <br /><br />
                <strong>Current Free Demo Limits:</strong>
                <ul style={{ margin: '6px 0 0 18px', padding: 0 }}>
                  <li>Max Audio Duration: <strong>5 minutes</strong></li>
                  <li>Max File Size: <strong>50 MB</strong></li>
                </ul>
              </div>
            </div>
          </div>

          <div style={{
            background: '#faf5ff',
            border: '1px solid #e9d5ff',
            borderRadius: 14,
            padding: '14px 16px',
            marginBottom: 20,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}>
            <div>
              <div style={{ fontSize: 13.5, fontWeight: 700, color: '#3b0764' }}>
                Premium Tier Membership ($19/mo)
              </div>
              <div style={{ fontSize: 12, color: '#64748b' }}>
                Will unlock up to 3-hour audio processing &amp; 500 MB files once launched.
              </div>
            </div>
            <Lock size={20} color="#7e22ce" style={{ flexShrink: 0, marginLeft: 10 }} />
          </div>

          <button
            onClick={onClose}
            style={{
              width: '100%',
              padding: '12px 16px',
              borderRadius: 12,
              background: 'linear-gradient(135deg, #c084fc, #a855f7)',
              color: '#ffffff',
              border: 'none',
              fontWeight: 700,
              fontSize: 14.5,
              cursor: 'pointer',
              boxShadow: '0 4px 14px rgba(168, 85, 247, 0.35)',
            }}
          >
            I Understand (Stay on Free Demo)
          </button>
        </div>
      </div>
    </div>
  );
}


const inputStyle = {
  width: '100%', padding: '10px 12px', borderRadius: 10,
  border: '1px solid #cbd5e1', background: '#fff', fontSize: 14, color: '#111',
  outline: 'none', boxSizing: 'border-box',
};

const featureRowStyle = {
  display: 'flex', alignItems: 'flex-start', gap: 10, fontSize: 13.5,
};
