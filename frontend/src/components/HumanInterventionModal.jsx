import React from 'react';
import { ShieldAlert, CheckCircle, XCircle, LogIn } from 'lucide-react';

export default function HumanInterventionModal({ intervention, onRespond }) {
  if (!intervention) return null;

  const isCaptcha = intervention.intervention_type === 'CAPTCHA';
  const isLogin = intervention.intervention_type === 'ACCOUNT_LOGIN_REQUIRED';

  let title = 'Action Approval Required';
  let iconColor = '#d97706';
  let IconComponent = ShieldAlert;

  if (isCaptcha) {
    title = 'Human Verification / CAPTCHA Detected';
    iconColor = '#d97706';
    IconComponent = ShieldAlert;
  } else if (isLogin) {
    title = 'Google Account Sign-In Required';
    iconColor = '#2563eb';
    IconComponent = LogIn;
  }

  return (
    <div className="modal-backdrop">
      <div className="modal-card">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: iconColor }}>
          <IconComponent size={26} />
          <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#0f172a' }}>
            {title}
          </h3>
        </div>

        <p style={{ color: '#334155', fontSize: '0.95rem', lineHeight: '1.5' }}>
          {intervention.prompt}
        </p>

        {isCaptcha && (
          <div style={{ fontSize: '0.85rem', color: '#1e293b', background: '#fef3c7', padding: '0.85rem', borderRadius: '8px', border: '1px solid #fcd34d' }}>
            <strong>How to Solve:</strong> Simply click directly on the <strong>Live Browser Preview</strong> below to check the CAPTCHA box or select images. Once solved, click <strong>Resume Task</strong>.
          </div>
        )}

        {isLogin && (
          <div style={{ fontSize: '0.85rem', color: '#1e3a8a', background: '#eff6ff', padding: '0.85rem', borderRadius: '8px', border: '1px solid #bfdbfe' }}>
            <strong>One-Time Setup:</strong> Sign in to your Google Account directly in the <strong>Live Browser Preview</strong> below. Once signed in, click <strong>Continue</strong>. Your session will be securely saved so you won't need to sign in again!
          </div>
        )}

        <div className="modal-actions" style={{ marginTop: '0.5rem' }}>
          <button className="btn-reject" onClick={() => onRespond(false)}>
            <XCircle size={15} style={{ display: 'inline', marginRight: '4px' }} /> Cancel Task
          </button>
          <button className="btn-approve" onClick={() => onRespond(true)}>
            <CheckCircle size={15} style={{ display: 'inline', marginRight: '4px' }} /> {isCaptcha ? 'Resume Task' : isLogin ? 'Continue (Signed In)' : 'Approve Action'}
          </button>
        </div>
      </div>
    </div>
  );
}
