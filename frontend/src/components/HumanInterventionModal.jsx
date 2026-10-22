import React from 'react';
import { ShieldAlert, CheckCircle, XCircle } from 'lucide-react';

export default function HumanInterventionModal({ intervention, onRespond }) {
  if (!intervention) return null;

  const isCaptcha = intervention.intervention_type === 'CAPTCHA';

  return (
    <div className="modal-backdrop">
      <div className="modal-card">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#d97706' }}>
          <ShieldAlert size={26} />
          <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#0f172a' }}>
            {isCaptcha ? 'Human Verification / CAPTCHA Detected' : 'Action Approval Required'}
          </h3>
        </div>

        <p style={{ color: '#334155', fontSize: '0.95rem', lineHeight: '1.5' }}>
          {intervention.prompt}
        </p>

        {isCaptcha && (
          <div style={{ fontSize: '0.85rem', color: '#1e293b', background: '#fef3c7', padding: '0.85rem', borderRadius: '8px', border: '1px solid #fcd34d' }}>
            <strong>How to Solve:</strong> Simply click directly on the <strong>Embedded Chrome Browser</strong> below to check the CAPTCHA box or select images. Once solved, click <strong>Resume Task</strong>.
          </div>
        )}

        <div className="modal-actions" style={{ marginTop: '0.5rem' }}>
          <button className="btn-reject" onClick={() => onRespond(false)}>
            <XCircle size={15} style={{ display: 'inline', marginRight: '4px' }} /> Cancel Task
          </button>
          <button className="btn-approve" onClick={() => onRespond(true)}>
            <CheckCircle size={15} style={{ display: 'inline', marginRight: '4px' }} /> {isCaptcha ? 'Resume Task' : 'Approve Action'}
          </button>
        </div>
      </div>
    </div>
  );
}
