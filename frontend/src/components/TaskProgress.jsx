import React, { useRef, useEffect } from 'react';
import {
  Activity,
  Pause,
  Play,
  Eye,
  Cpu,
  Zap,
  ShieldAlert,
  CheckCircle2,
  XCircle,
  Search,
  MousePointer,
  Edit3,
  Globe,
  Layers,
  Sparkles,
  Check,
  RotateCcw
} from 'lucide-react';

export default function TaskProgress({ taskState, events, onPauseTask, onResumeTask }) {
  if (!taskState) return null;

  const status = taskState.status || 'CREATED';
  const isPaused = status === 'PAUSED';
  const isActive = ['PLANNING', 'RUNNING', 'OBSERVING'].includes(status);
  const badgeClass = `badge badge-${status.toLowerCase()}`;
  const stepsEndRef = useRef(null);
  const feedRef = useRef(null);
  const isFeedAtBottomRef = useRef(true);

  // Helper for live real-time pipeline status text & icon
  const renderLiveStatusIndicator = () => {
    switch (status) {
      case 'OBSERVING':
        return (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#7e22ce', backgroundColor: '#f3e8ff', padding: '0.4rem 0.8rem', borderRadius: '6px', fontSize: '0.85rem', fontWeight: '600' }}>
            <Eye size={16} className="animate-spin" /> Analyzing Live Page & Interactive Elements...
          </div>
        );
      case 'PLANNING':
        return (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#0369a1', backgroundColor: '#e0f2fe', padding: '0.4rem 0.8rem', borderRadius: '6px', fontSize: '0.85rem', fontWeight: '600' }}>
            <Cpu size={16} /> AI Reasoner Planning Next Step...
          </div>
        );
      case 'RUNNING':
        return (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#1d4ed8', backgroundColor: '#dbeafe', padding: '0.4rem 0.8rem', borderRadius: '6px', fontSize: '0.85rem', fontWeight: '600' }}>
            <Zap size={16} /> Executing Action in Live Browser...
          </div>
        );
      case 'WAITING_FOR_HUMAN':
        return (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#b45309', backgroundColor: '#fef3c7', padding: '0.4rem 0.8rem', borderRadius: '6px', fontSize: '0.85rem', fontWeight: '600' }}>
            <ShieldAlert size={16} /> Verification / Human Input Required
          </div>
        );
      case 'COMPLETED':
        return (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#047857', backgroundColor: '#d1fae5', padding: '0.4rem 0.8rem', borderRadius: '6px', fontSize: '0.85rem', fontWeight: '600' }}>
            <CheckCircle2 size={16} /> Goal Successfully Achieved!
          </div>
        );
      case 'FAILED':
        return (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#b91c1c', backgroundColor: '#fee2e2', padding: '0.4rem 0.8rem', borderRadius: '6px', fontSize: '0.85rem', fontWeight: '600' }}>
            <XCircle size={16} /> Task Failed
          </div>
        );
      default:
        return null;
    }
  };

  const getActionMeta = (type) => {
    const norm = String(type || '').toLowerCase();
    if (norm.includes('search')) {
      return { icon: <Search size={13} color="#2563eb" />, label: 'Search', bg: '#eff6ff', color: '#1d4ed8' };
    }
    if (norm.includes('click')) {
      return { icon: <MousePointer size={13} color="#7c3aed" />, label: 'Click', bg: '#f5f3ff', color: '#6d28d9' };
    }
    if (norm.includes('fill') || norm.includes('input') || norm.includes('type')) {
      return { icon: <Edit3 size={13} color="#2563eb" />, label: 'Input', bg: '#eff6ff', color: '#1d4ed8' };
    }
    if (norm.includes('navigate') || norm.includes('goto')) {
      return { icon: <Globe size={13} color="#2563eb" />, label: 'Navigate', bg: '#eff6ff', color: '#1d4ed8' };
    }
    if (norm.includes('select')) {
      return { icon: <Layers size={13} color="#4f46e5" />, label: 'Select', bg: '#eef2ff', color: '#4338ca' };
    }
    if (norm.includes('extract') || norm.includes('finish')) {
      return { icon: <CheckCircle2 size={13} color="#2563eb" />, label: 'Extract', bg: '#eff6ff', color: '#1d4ed8' };
    }
    return { icon: <Sparkles size={13} color="#475569" />, label: type || 'Action', bg: '#f1f5f9', color: '#334155' };
  };

  // Filter out noisy internal background events (screenshots, frames) from the user-facing step list
  const userVisibleEvents = (events || []).filter(
    (e) => e && e.type !== 'SCREENSHOT_SAVED' && e.type !== 'BROWSER_FRAME' && !String(e.intent || '').toLowerCase().includes('screenshot')
  );

  const handleFeedScroll = (e) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
    isFeedAtBottomRef.current = scrollHeight - scrollTop - clientHeight <= 30;
  };

  useEffect(() => {
    if (feedRef.current && isFeedAtBottomRef.current) {
      feedRef.current.scrollTo({
        top: feedRef.current.scrollHeight,
        behavior: 'smooth'
      });
    }
  }, [userVisibleEvents.length]);

  return (
    <div className="card">
      <div className="card-header">
        <div className="card-title">
          <Activity size={18} color="#2563eb" />
          <span>Execution Steps</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {isActive && (
            <button
              onClick={onPauseTask}
              title="Pause Task Execution"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem',
                backgroundColor: '#d97706',
                color: 'white',
                border: 'none',
                padding: '0.35rem 0.8rem',
                borderRadius: '6px',
                fontSize: '0.8rem',
                fontWeight: '600',
                cursor: 'pointer'
              }}
            >
              <Pause size={14} /> Pause
            </button>
          )}

          {isPaused && (
            <button
              onClick={onResumeTask}
              title="Resume Task Execution"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem',
                backgroundColor: '#2563eb',
                color: 'white',
                border: 'none',
                padding: '0.35rem 0.8rem',
                borderRadius: '6px',
                fontSize: '0.8rem',
                fontWeight: '600',
                cursor: 'pointer'
              }}
            >
              <Play size={14} /> Resume
            </button>
          )}

          <span className={badgeClass}>{status}</span>
        </div>
      </div>

      {/* Live Pipeline Status Banner */}
      {renderLiveStatusIndicator()}

      <div
        className="event-feed"
        ref={feedRef}
        onScroll={handleFeedScroll}
        style={{ marginTop: '0.75rem' }}
      >
        {userVisibleEvents && userVisibleEvents.length > 0 ? (
          userVisibleEvents.map((evt, idx) => {
            if (evt.type === 'SUBTASK_COMPLETED') {
              return (
                <div key={idx} style={{
                  backgroundColor: '#eff6ff',
                  border: '1px solid #bfdbfe',
                  borderRadius: '10px',
                  padding: '0.85rem 1rem',
                  marginTop: '0.5rem',
                  marginBottom: '0.6rem',
                  boxShadow: '0 2px 6px rgba(37, 99, 235, 0.08)'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#1e40af', fontWeight: 700, fontSize: '0.9rem' }}>
                    <CheckCircle2 size={18} color="#2563eb" />
                    <span>{evt.title || `Subtask Milestone Achieved`}</span>
                  </div>
                  {evt.summary && (
                    <div style={{ fontSize: '0.85rem', color: '#1d4ed8', marginTop: '0.35rem', lineHeight: 1.5 }}>
                      {evt.summary}
                    </div>
                  )}
                  {evt.data && Object.keys(evt.data).length > 0 && (
                    <div style={{ marginTop: '0.5rem', display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
                      {Object.entries(evt.data).map(([k, v]) => (
                        <span key={k} style={{
                          fontSize: '0.75rem',
                          backgroundColor: '#ffffff',
                          border: '1px solid #d1fae5',
                          color: '#065f46',
                          padding: '0.2rem 0.5rem',
                          borderRadius: '4px',
                          fontWeight: 500
                        }}>
                          <strong>{k}:</strong> {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            }

            const meta = getActionMeta(evt.type || evt.action);
            const stepNum = evt.step || idx + 1;

            return (
              <div
                key={idx}
                style={{
                  backgroundColor: '#ffffff',
                  border: '1px solid #e2e8f0',
                  borderRadius: '10px',
                  padding: '0.85rem 1rem',
                  marginBottom: '0.6rem',
                  boxShadow: '0 1px 3px rgba(0, 0, 0, 0.03)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.4rem'
                }}
              >
                {/* Header row: Step pill, Action Tag, and Status Chip */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span style={{
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      backgroundColor: '#1e293b',
                      color: '#ffffff',
                      padding: '0.18rem 0.55rem',
                      borderRadius: '5px',
                      letterSpacing: '0.04em',
                      textTransform: 'uppercase'
                    }}>
                      Step {stepNum}
                    </span>
                    <span style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '0.35rem',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      backgroundColor: meta.bg,
                      color: meta.color,
                      padding: '0.18rem 0.55rem',
                      borderRadius: '5px'
                    }}>
                      {meta.icon}
                      {meta.label}
                    </span>
                  </div>

                  {/* Status Indicator Chip */}
                  {evt.success !== undefined ? (
                    evt.success ? (
                      <span style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '0.25rem',
                        fontSize: '0.72rem',
                        fontWeight: 600,
                        color: '#059669',
                        backgroundColor: '#d1fae5',
                        padding: '0.15rem 0.55rem',
                        borderRadius: '12px'
                      }}>
                        <Check size={12} strokeWidth={3} /> Completed
                      </span>
                    ) : (
                      <span style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '0.25rem',
                        fontSize: '0.72rem',
                        fontWeight: 600,
                        color: '#d97706',
                        backgroundColor: '#fef3c7',
                        padding: '0.15rem 0.55rem',
                        borderRadius: '12px'
                      }}>
                        <RotateCcw size={12} /> Auto-healing
                      </span>
                    )
                  ) : (
                    <span style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '0.3rem',
                      fontSize: '0.72rem',
                      fontWeight: 600,
                      color: '#2563eb',
                      backgroundColor: '#dbeafe',
                      padding: '0.15rem 0.55rem',
                      borderRadius: '12px'
                    }}>
                      <div style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: '#2563eb' }} /> Active
                    </span>
                  )}
                </div>

                {/* Clean human-readable step description / intent */}
                <div style={{
                  fontSize: '0.86rem',
                  color: '#334155',
                  lineHeight: 1.45,
                  fontWeight: 500,
                  marginTop: '0.15rem'
                }}>
                  {evt.intent || (evt.action ? `Performing ${evt.action} action on page` : 'Executing browser action')}
                </div>

                {/* Optional URL indicator if step navigated */}
                {evt.url && (
                  <div style={{
                    fontSize: '0.75rem',
                    color: '#64748b',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.35rem',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap'
                  }}>
                    <Globe size={12} color="#94a3b8" />
                    <span style={{ textDecoration: 'none', color: '#0284c7' }}>{evt.url}</span>
                  </div>
                )}
              </div>
            );
          })
        ) : (
          <div style={{ color: '#64748b', fontStyle: 'italic', padding: '1rem' }}>
            Initializing reasoning loop...
          </div>
        )}
        <div ref={stepsEndRef} style={{ height: '1px' }} />
      </div>
    </div>
  );
}
