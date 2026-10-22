import React from 'react';
import { Cpu, LogOut, User, Sparkles } from 'lucide-react';

export default function Navbar({ user, onLogout, onGoHome }) {
  return (
    <header className="navbar" style={{
      height: '62px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 1.5rem',
      backgroundColor: '#ffffff',
      borderBottom: '1px solid #e2e8f0',
      boxShadow: '0 1px 3px rgba(15, 23, 42, 0.03)',
      position: 'sticky',
      top: 0,
      zIndex: 100
    }}>
      {/* Professional Brand Identity */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <div
          onClick={onGoHome}
          style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', cursor: onGoHome ? 'pointer' : 'default', userSelect: 'none' }}
          title={onGoHome ? "Back to Home Page" : undefined}
        >
          <img
            src="/logo.png"
            alt="Nexagent"
            style={{
              width: 30,
              height: 30,
              borderRadius: '7px',
              objectFit: 'cover',
              boxShadow: '0 2px 6px rgba(15, 23, 42, 0.12)',
              flexShrink: 0
            }}
          />
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <span style={{
              fontWeight: 800,
              fontSize: '1.1rem',
              color: '#0f172a',
              letterSpacing: '-0.02em',
              fontFamily: 'Inter, system-ui, -apple-system, sans-serif'
            }}>
              Nex<span style={{
                background: 'linear-gradient(135deg, #2563eb 0%, #7c3aed 100%)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent'
              }}>agent</span>
            </span>

          </div>
        </div>


        {onGoHome && (
          <button
            type="button"
            onClick={onGoHome}
            style={{
              background: 'transparent',
              border: '1px solid #e2e8f0',
              borderRadius: '6px',
              padding: '0.24rem 0.55rem',
              fontSize: '0.75rem',
              fontWeight: 600,
              color: '#475569',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.3rem'
            }}
          >
            ← Home
          </button>
        )}
      </div>

      {/* Right Controls: Model Badge & User Session */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
        {/* NVIDIA Nemotron 3.5 | Stream Active Pill */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.45rem',
          background: '#ffffff',
          border: '1px solid #e2e8f0',
          padding: '0.3rem 0.75rem',
          borderRadius: '20px',
          color: '#334155',
          fontSize: '0.78rem',
          fontWeight: 600
        }}>
          <span style={{
            width: 7,
            height: 7,
            borderRadius: '50%',
            backgroundColor: '#22c55e',
            display: 'inline-block'
          }} />
          <span>NVIDIA Nemotron 3.5</span>
          <span style={{ color: '#cbd5e1', margin: '0 0.15rem' }}>|</span>
          <span style={{ color: '#059669', fontSize: '0.74rem' }}>Stream Active</span>
        </div>

        {user && (() => {
          const displayName = user.guest
            ? 'Guest Session'
            : (user.name || (user.email ? user.email.split('@')[0] : 'User'));
          const initial = displayName ? displayName.charAt(0).toUpperCase() : 'U';

          return (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              {/* User Session Pill with Blue circular avatar */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.45rem',
                  backgroundColor: '#ffffff',
                  border: '1px solid #e2e8f0',
                  padding: '0.25rem 0.65rem 0.25rem 0.35rem',
                  borderRadius: '20px',
                  fontSize: '0.8rem',
                  fontWeight: 600,
                  color: '#1e293b'
                }}
                title={user.email ? `${displayName} (${user.email})` : undefined}
              >
                <div style={{
                  width: 22,
                  height: 22,
                  borderRadius: '50%',
                  backgroundColor: '#2563eb',
                  color: '#ffffff',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '0.7rem',
                  fontWeight: 700
                }}>
                  {initial}
                </div>
                <span>{displayName}</span>
              </div>

              {/* Professional Neutral Logout Button */}
              <button
                type="button"
                onClick={onLogout}
                title="Log out of session"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  backgroundColor: '#ffffff',
                  border: '1px solid #e2e8f0',
                  color: '#64748b',
                  padding: '0.32rem 0.7rem',
                  borderRadius: '8px',
                  fontSize: '0.78rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.18s ease',
                  boxShadow: '0 1px 2px rgba(15, 23, 42, 0.03)'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = '#fef2f2';
                  e.currentTarget.style.borderColor = '#fecaca';
                  e.currentTarget.style.color = '#dc2626';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = '#ffffff';
                  e.currentTarget.style.borderColor = '#e2e8f0';
                  e.currentTarget.style.color = '#64748b';
                }}
              >
                <LogOut size={13} strokeWidth={2} />
                <span>Logout</span>
              </button>
            </div>
          );
        })()}
      </div>
    </header>
  );
}
