import React from 'react';
import { Trash2, Plus, X } from 'lucide-react';

export default function TaskHistory({ tasks = [], onSelectTask, activeTaskId, onClearHistory, onNewTask, onDeleteTask }) {
  const activeCount = tasks.filter(t => !['COMPLETED', 'FAILED', 'CANCELLED'].includes(t.status)).length || (tasks.length ? 1 : 0);

  // Periodic tick to automatically update relative times (e.g. 'Just now' -> '2m ago')
  const [, setTick] = React.useState(0);
  React.useEffect(() => {
    const timer = setInterval(() => setTick(t => t + 1), 30000);
    return () => clearInterval(timer);
  }, []);

  const formatRelativeTime = (dateStr) => {
    if (!dateStr) return 'Just now';
    const normalized = (dateStr.endsWith('Z') || dateStr.includes('+')) ? dateStr : `${dateStr}Z`;
    const date = new Date(normalized);
    const validDate = isNaN(date.getTime()) ? new Date(dateStr) : date;
    if (isNaN(validDate.getTime())) return 'Just now';

    const now = new Date();
    const diffSec = Math.floor((now - validDate) / 1000);
    if (diffSec < 0 || diffSec < 60) return 'Just now';
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    if (diffSec < 172800) return 'Yesterday';
    return validDate.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  };

  const getSubMeta = (task) => {
    const url = task.current_url || '';
    let domain = '';
    try {
      if (url && url !== 'about:blank') {
        domain = new URL(url).hostname.replace('www.', '');
      }
    } catch {}
    if (!domain && task.goal) {
      try {
        const match = task.goal.match(/https?:\/\/([^\/\s]+)/);
        if (match) domain = match[1].replace('www.', '');
      } catch {}
    }
    if (!domain && task.goal) {
      if (/daraz/i.test(task.goal)) domain = 'daraz.pk';
      else if (/amazon/i.test(task.goal)) domain = 'amazon.com';
      else if (/techcrunch/i.test(task.goal)) domain = 'techcrunch.com';
      else if (/github/i.test(task.goal)) domain = 'github.com';
      else if (/docs\.google\.com|forms/i.test(task.goal)) domain = 'docs.google.com';
      else domain = 'web search';
    }

    const isForm = /form|survey|fill/i.test(task.goal || '') || domain.includes('google.com') || domain.includes('forms');
    const items = task.result?.data?.items || task.result?.extracted_data?.items;

    if (isForm) {
      return `${domain || 'web'} • Form submitted`;
    }
    if (Array.isArray(items) && items.length > 0) {
      const isProduct = items.some(it => it && typeof it === 'object' && (it.price || it.cost || it.amount));
      return `${domain || 'web'} • ${items.length} ${isProduct ? 'products' : 'records'} parsed`;
    }
    if (task.status === 'COMPLETED') {
      return `${domain || 'web'} • Completed`;
    }
    return domain || 'web task';
  };

  return (
    <aside className="session-sidebar" style={{
      width: '260px',
      backgroundColor: '#f8fafc',
      borderRight: '1px solid #e2e8f0',
      display: 'flex',
      flexDirection: 'column',
      padding: '0.9rem',
      height: '100%',
      boxSizing: 'border-box'
    }}>
      {/* 1. New Task Button with ⌘K Badge */}
      {onNewTask && (
        <button
          type="button"
          onClick={onNewTask}
          style={{
            backgroundColor: '#2563eb',
            color: '#ffffff',
            border: 'none',
            borderRadius: '8px',
            padding: '0.6rem 0.9rem',
            fontSize: '0.85rem',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            cursor: 'pointer',
            boxShadow: '0 1px 3px rgba(37, 99, 235, 0.25)',
            marginBottom: '1.25rem',
            transition: 'background 0.15s ease'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
            <Plus size={16} strokeWidth={2.5} />
            <span>New task</span>
          </div>
          <span style={{
            fontSize: '0.7rem',
            backgroundColor: 'rgba(255, 255, 255, 0.2)',
            padding: '0.1rem 0.4rem',
            borderRadius: '4px',
            letterSpacing: '0.04em'
          }}>
            ⌘K
          </span>
        </button>
      )}


      {/* 3. Session Items List */}
      <div className="session-list" style={{
        flex: 1,
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.6rem',
        paddingRight: '2px'
      }}>
        {tasks && tasks.length > 0 ? (
          tasks.map((task, idx) => {
            const isActive = task.id === activeTaskId || (task.session_task_ids && task.session_task_ids.includes(activeTaskId));
            const isCompleted = (task.status || '').toUpperCase() === 'COMPLETED';

            return (
              <div
                key={task.id || idx}
                onClick={() => onSelectTask(task)}
                style={{
                  backgroundColor: isActive ? '#ffffff' : '#f8fafc',
                  border: `1px solid ${isActive ? '#93c5fd' : '#e2e8f0'}`,
                  borderRadius: '10px',
                  padding: '0.75rem 0.85rem',
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.35rem',
                  boxShadow: isActive ? '0 2px 6px rgba(37, 99, 235, 0.08)' : 'none',
                  position: 'relative',
                  transition: 'all 0.15s ease'
                }}
              >
                {/* Top Row: Status Pill + Timestamp + Delete Button */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{
                    fontSize: '0.62rem',
                    fontWeight: 800,
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                    padding: '0.15rem 0.45rem',
                    borderRadius: '4px',
                    backgroundColor: isCompleted ? '#dcfce7' : (isActive ? '#dbeafe' : '#f1f5f9'),
                    color: isCompleted ? '#166534' : (isActive ? '#1d4ed8' : '#64748b'),
                  }}>
                    {isCompleted ? 'COMPLETED' : (isActive ? (task.status || 'ACTIVE') : 'ARCHIVED')}
                  </span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{ fontSize: '0.7rem', color: '#94a3b8', fontWeight: 500 }}>
                      {formatRelativeTime(task.updated_at || task.created_at || task.completed_at)}
                    </span>
                    {onDeleteTask && (
                      <button
                        type="button"
                        title="Delete this task"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (window.confirm("Are you sure you want to delete this task?")) {
                            onDeleteTask(task.id);
                          }
                        }}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: '#94a3b8',
                          cursor: 'pointer',
                          padding: '3px',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          borderRadius: '4px',
                          transition: 'all 0.15s ease'
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.color = '#ef4444';
                          e.currentTarget.style.backgroundColor = '#fee2e2';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.color = '#94a3b8';
                          e.currentTarget.style.backgroundColor = 'transparent';
                        }}
                      >
                        <Trash2 size={13} />
                      </button>
                    )}
                  </div>
                </div>

                {/* Task Title */}
                <div style={{
                  fontSize: '0.84rem',
                  fontWeight: 700,
                  color: '#0f172a',
                  lineHeight: 1.35,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical'
                }}>
                  {task.goal || 'Unnamed task'}
                </div>

                {/* Subtitle: Domain • Items Parsed */}
                <div style={{ fontSize: '0.72rem', color: '#64748b', fontWeight: 500 }}>
                  {getSubMeta(task)}
                </div>
              </div>
            );
          })
        ) : (
          <div style={{
            textAlign: 'center',
            padding: '2.5rem 1rem',
            color: '#94a3b8',
            fontSize: '0.8rem'
          }}>
            No recent sessions
          </div>
        )}
      </div>

      {/* 4. Bottom Footer: Browser runtime & Clear history */}
      <div style={{
        marginTop: 'auto',
        paddingTop: '0.85rem',
        borderTop: '1px solid #e2e8f0',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.65rem'
      }}>

        {/* Clear History Button */}
        {onClearHistory && (
          <button
            type="button"
            onClick={onClearHistory}
            style={{
              backgroundColor: '#ffffff',
              border: '1px solid #e2e8f0',
              borderRadius: '7px',
              padding: '0.45rem 0.75rem',
              color: '#64748b',
              fontSize: '0.78rem',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.4rem',
              cursor: 'pointer',
              transition: 'background 0.15s ease'
            }}
          >
            <Trash2 size={13} />
            <span>Clear history</span>
          </button>
        )}
      </div>
    </aside>
  );
}
