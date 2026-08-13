import React from 'react';
import { Link } from 'react-router-dom';

export default function AppNavbar() {
  return (
    <div style={{
      position: 'sticky', top: 0, zIndex: 40,
      background: '#ffffff', borderBottom: '1px solid #e2e8f0',
    }}>
      <div style={{
        maxWidth: 1440, margin: '0 auto', padding: '14px 24px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: 12, textDecoration: 'none', color: '#111' }}>
          <img
            src="/icarkno%20logo.png"
            alt="icarKno"
            style={{ width: 36, height: 36, objectFit: 'contain', borderRadius: 10 }}
          />
          <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.15 }}>
            <span style={{ fontFamily: "'Manrope',sans-serif", fontWeight: 800, fontSize: 15.5 }}>Meeting Summariser</span>
            <span style={{ fontSize: 11.5, color: '#94a3b8' }}>by Carnot Research Pvt Ltd</span>
          </div>
        </Link>
        <Link to="/" style={{
          fontSize: 14, fontWeight: 500, color: '#64748b', textDecoration: 'none',
        }}>← Back to home</Link>
      </div>
    </div>
  );
}
