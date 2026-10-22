import React, { useState, useRef } from 'react';
import { Send, Paperclip, FileText, X } from 'lucide-react';

export default function TaskInput({
  onSubmit,
  isLoading,
  disabled = false,
  placeholder = 'Message Nexagent',
  submitLabel,
  allowFileUpload = true
}) {
  const [goal, setGoal] = useState('');
  const [attachedFile, setAttachedFile] = useState(null);
  const fileInputRef = useRef(null);

  const isInputBlocked = disabled || isLoading;

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const allowedExtensions = ['.txt', '.text', '.csv', '.json', '.md'];
    const lowerName = file.name.toLowerCase();
    const isAllowed = allowedExtensions.some((ext) => lowerName.endsWith(ext));

    if (!isAllowed) {
      alert('Supported text file formats: .txt, .csv, .json, .md');
      e.target.value = '';
      return;
    }

    setAttachedFile(file);
    e.target.value = '';
  };

  const removeAttachedFile = () => {
    setAttachedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if ((goal.trim() || attachedFile) && !isInputBlocked) {
      const textToSubmit = goal.trim() || (attachedFile ? `Process attached file: ${attachedFile.name}` : '');
      await onSubmit(textToSubmit, attachedFile);
      setGoal('');
      setAttachedFile(null);
    }
  };

  const formatFileSize = (bytes) => {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  return (
    <div className={`task-input-card composer-card ${isInputBlocked ? 'composer-disabled' : ''}`}>
      {attachedFile && (
        <div className="attached-file-badge">
          <div className="attached-file-info">
            <FileText size={15} className="attached-file-icon" />
            <span className="attached-file-name">{attachedFile.name}</span>
            <span className="attached-file-size">({formatFileSize(attachedFile.size)})</span>
          </div>
          <button
            type="button"
            className="attached-file-remove"
            onClick={removeAttachedFile}
            title="Remove attached file"
            disabled={isInputBlocked}
          >
            <X size={14} />
          </button>
        </div>
      )}

      <form onSubmit={handleSubmit} className="input-group">
        {allowFileUpload && (
          <>
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              accept=".txt,.text,.csv,.json,.md,text/plain"
              style={{ display: 'none' }}
              disabled={isInputBlocked}
            />
            <button
              type="button"
              className={`attach-btn ${attachedFile ? 'active' : ''}`}
              onClick={() => fileInputRef.current?.click()}
              title="Attach .txt file context"
              disabled={isInputBlocked}
            >
              <Paperclip size={18} />
            </button>
          </>
        )}

        <div style={{ position: 'relative', flex: 1, display: 'flex', alignItems: 'center' }}>
          <textarea
            className="task-textarea"
            placeholder={placeholder}
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            rows={1}
            disabled={isInputBlocked}
            style={{
              width: '100%',
              resize: 'none',
              paddingRight: '60px',
              fontFamily: 'inherit',
              fontSize: '0.88rem'
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(e);
              }
            }}
          />
        </div>

        <button
          type="submit"
          className="submit-btn"
          disabled={(!goal.trim() && !attachedFile) || isInputBlocked}
          style={{
            backgroundColor: (!goal.trim() && !attachedFile) || isInputBlocked ? '#94a3b8' : '#2563eb',
            color: '#ffffff',
            border: 'none',
            borderRadius: '8px',
            padding: '0.55rem 1rem',
            fontSize: '0.85rem',
            fontWeight: 700,
            display: 'flex',
            alignItems: 'center',
            gap: '0.45rem',
            cursor: (!goal.trim() && !attachedFile) || isInputBlocked ? 'not-allowed' : 'pointer',
            transition: 'background 0.15s ease',
            boxShadow: '0 1px 3px rgba(37, 99, 235, 0.25)'
          }}
        >
          <Send size={15} strokeWidth={2.5} />
          <span>{isLoading ? 'Working...' : (submitLabel || 'Send')}</span>
        </button>
      </form>
    </div>
  );
}
