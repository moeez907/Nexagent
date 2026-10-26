import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Globe, Monitor,
  ArrowLeft, ArrowRight, RotateCw, Lock, ShieldCheck, Plus, X, Home
} from 'lucide-react';

export default function BrowserPreview({
  currentUrl,
  screenshotUrl,
  onInteract,
  taskStatus,
  pendingIntervention
}) {
  const [navUrl, setNavUrl] = useState('');
  const [liveFrame, setLiveFrame] = useState(null);
  const [lastClick, setLastClick] = useState(null);
  const [isSending, setIsSending] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [displayedSrc, setDisplayedSrc] = useState(screenshotUrl || null);
  const [viewMode, setViewMode] = useState('vnc');

  const containerRef = useRef(null);
  const imageRef = useRef(null);
  const webviewRef = useRef(null);
  const isDesktop = Boolean(window.autonomousWebAgent?.desktop);

  const isDraggingRef = useRef(false);
  const dragStartRef = useRef({ x: 0, y: 0 });
  const hasDraggedRef = useRef(false);
  const lastMoveTimeRef = useRef(0);
  const wheelAccumulatorRef = useRef(0);
  const wheelTimerRef = useRef(null);

  useEffect(() => {
    if (currentUrl) {
      setNavUrl(currentUrl);
    }
  }, [currentUrl]);

  useEffect(() => {
    const next = liveFrame || screenshotUrl;
    if (next) {
      setDisplayedSrc(next);
      if (imageRef.current) {
        imageRef.current.src = next;
      }
    }
  }, [liveFrame, screenshotUrl]);

  // High-performance direct frame rendering (zero React re-render jank)
  useEffect(() => {
    const handleLiveFrame = (e) => {
      const frameData = e.detail;
      if (!frameData) return;
      if (imageRef.current) {
        imageRef.current.src = frameData;
      }
      setDisplayedSrc((prev) => prev || frameData);
    };

    window.addEventListener('awa:live_browser_frame', handleLiveFrame);
    return () => window.removeEventListener('awa:live_browser_frame', handleLiveFrame);
  }, []);

  // Extract clean domain name for Chrome tab title
  const getTabTitle = () => {
    if (!currentUrl || currentUrl === 'about:blank') return 'New Tab';
    try {
      const u = new URL(currentUrl);
      return u.hostname.replace('www.', '');
    } catch {
      return currentUrl;
    }
  };

  const getStatusBadge = () => {
    if (pendingIntervention) {
      return {
        text: 'Action Required (CAPTCHA / Login)',
        color: '#d97706',
        bg: '#fef3c7',
        border: '#fde68a',
        pulse: true,
      };
    }
    if (taskStatus === 'PLANNING') {
      return {
        text: 'AI Analyzing & Planning...',
        color: '#7c3aed',
        bg: '#ede9fe',
        border: '#ddd6fe',
        pulse: true,
      };
    }
    if (taskStatus === 'RUNNING') {
      return {
        text: 'Chrome Executing Action...',
        color: '#059669',
        bg: '#d1fae5',
        border: '#a7f3d0',
        pulse: true,
      };
    }
    return {
      text: 'Live Chrome Session Active',
      color: '#0284c7',
      bg: '#e0f2fe',
      border: '#bae6fd',
      pulse: false,
    };
  };

  const statusBadge = getStatusBadge();

  const executeInteraction = useCallback(async (payload) => {
    if (!onInteract) return;
    // Only lock UI on full-page navigations, not during high-frequency mouse movements or typing
    const isHeavy = ['navigate', 'reload', 'back', 'forward'].includes(payload.action);
    if (isHeavy) setIsSending(true);
    try {
      const res = await onInteract(payload);
      if (res && res.frame_data) {
        if (imageRef.current) {
          imageRef.current.src = res.frame_data;
        }
        setLiveFrame(res.frame_data);
      }
      return res;
    } finally {
      if (isHeavy) setIsSending(false);
    }
  }, [onInteract]);

  const getRatiosFromEvent = (e) => {
    const target = imageRef.current || containerRef.current;
    if (!target) return { xRatio: 0.5, yRatio: 0.5, pixelX: 0, pixelY: 0 };
    const rect = target.getBoundingClientRect();
    const x = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
    const y = Math.max(0, Math.min(rect.height, e.clientY - rect.top));
    return {
      xRatio: rect.width > 0 ? Number((x / rect.width).toFixed(4)) : 0.5,
      yRatio: rect.height > 0 ? Number((y / rect.height).toFixed(4)) : 0.5,
      pixelX: x,
      pixelY: y,
    };
  };

  // Mouse Down - Records start position and prepares for click or slider drag
  const handleMouseDown = async (e) => {
    if (e.button !== 0) return; // Only primary button
    if (e.cancelable) e.preventDefault();

    if (containerRef.current) {
      containerRef.current.focus();
    }

    const { xRatio, yRatio, pixelX, pixelY } = getRatiosFromEvent(e);

    isDraggingRef.current = true;
    setIsDragging(true);
    dragStartRef.current = { x: e.clientX, y: e.clientY, xRatio, yRatio };
    hasDraggedRef.current = false;
    lastMoveTimeRef.current = Date.now();

    setLastClick({ x: pixelX, y: pixelY });
    setTimeout(() => setLastClick(null), 1200);
  };

  // Mouse Move - Smooth dragging for Slider CAPTCHAs, puzzle widgets, and scroll bars
  const handleMouseMove = useCallback((e) => {
    if (!isDraggingRef.current) return;
    e.preventDefault();

    const dist = Math.hypot(e.clientX - dragStartRef.current.x, e.clientY - dragStartRef.current.y);

    // Only engage drag mode if moved more than 4 pixels
    if (dist > 4 && !hasDraggedRef.current) {
      hasDraggedRef.current = true;
      // Send mousedown from the initial anchor point
      executeInteraction({ action: 'mousedown', x_ratio: dragStartRef.current.xRatio, y_ratio: dragStartRef.current.yRatio });
    }

    if (!hasDraggedRef.current) return;

    const now = Date.now();
    // 25ms throttle (~40fps) for fluid slider movement without overwhelming websocket
    if (now - lastMoveTimeRef.current < 25) return;
    lastMoveTimeRef.current = now;

    const { xRatio, yRatio, pixelX, pixelY } = getRatiosFromEvent(e);
    setLastClick({ x: pixelX, y: pixelY });
    executeInteraction({ action: 'mousemove', x_ratio: xRatio, y_ratio: yRatio });
  }, [executeInteraction]);

  // Mouse Up - If dragged, releases slider (mouseup). If stationary, fires clean click (click)
  const handleMouseUp = useCallback((e) => {
    if (!isDraggingRef.current) return;
    e.preventDefault();
    isDraggingRef.current = false;
    setIsDragging(false);

    const { xRatio, yRatio } = getRatiosFromEvent(e);

    if (hasDraggedRef.current) {
      // Completed slider drag
      executeInteraction({ action: 'mouseup', x_ratio: xRatio, y_ratio: yRatio });
    } else {
      // Stationary click (buttons, checkboxes, captcha verification, links)
      executeInteraction({ action: 'click', x_ratio: xRatio, y_ratio: yRatio });
    }
  }, [executeInteraction]);

  // Global window listeners for drag continuation even if pointer moves slightly outside preview
  useEffect(() => {
    const handleGlobalMouseMove = (e) => {
      if (isDraggingRef.current) {
        handleMouseMove(e);
      }
    };

    const handleGlobalMouseUp = (e) => {
      if (isDraggingRef.current) {
        handleMouseUp(e);
      }
    };

    window.addEventListener('mousemove', handleGlobalMouseMove);
    window.addEventListener('mouseup', handleGlobalMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleGlobalMouseMove);
      window.removeEventListener('mouseup', handleGlobalMouseUp);
    };
  }, [handleMouseMove, handleMouseUp]);

  // Double Click Support
  const handleDoubleClick = (e) => {
    if (e.cancelable) e.preventDefault();
    const { xRatio, yRatio } = getRatiosFromEvent(e);
    executeInteraction({ action: 'double_click', x_ratio: xRatio, y_ratio: yRatio });
  };

  // Mouse Wheel - Real cursor-targeted scrolling
  const handleWheel = (e) => {
    if (e.cancelable) e.preventDefault();
    if (!onInteract) return;

    const { xRatio, yRatio } = getRatiosFromEvent(e);
    wheelAccumulatorRef.current += e.deltaY;

    if (!wheelTimerRef.current) {
      wheelTimerRef.current = setTimeout(() => {
        const delta = Math.round(wheelAccumulatorRef.current);
        wheelAccumulatorRef.current = 0;
        wheelTimerRef.current = null;
        if (Math.abs(delta) > 5) {
          executeInteraction({
            action: 'scroll',
            delta_y: delta,
            x_ratio: xRatio,
            y_ratio: yRatio
          });
        }
      }, 20);
    }
  };

  // Keyboard Typing & Special Keys
  const handleContainerKeyDown = async (e) => {
    if (['ArrowUp', 'ArrowDown', 'Space'].includes(e.code)) {
      e.preventDefault();
    }

    if (!onInteract) return;

    if (e.key === 'Enter') {
      executeInteraction({ action: 'press', key: 'Enter' });
    } else if (e.key === 'Backspace') {
      executeInteraction({ action: 'press', key: 'Backspace' });
    } else if (e.key === 'Tab') {
      e.preventDefault();
      executeInteraction({ action: 'press', key: 'Tab' });
    } else if (e.key === 'Escape') {
      executeInteraction({ action: 'press', key: 'Escape' });
    } else if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Delete'].includes(e.key)) {
      executeInteraction({ action: 'press', key: e.key });
    } else if (e.key === ' ' || (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey)) {
      executeInteraction({ action: 'type', text: e.key });
    }
  };

  const handleNavSubmit = async (e) => {
    e.preventDefault();
    if (!navUrl.trim()) return;
    if (isDesktop && webviewRef.current) {
      const target = navUrl.match(/^https?:\/\//) ? navUrl.trim() : `https://${navUrl.trim()}`;
      await webviewRef.current.loadURL(target);
      return;
    }
    await executeInteraction({ action: 'navigate', url: navUrl.trim() });
  };

  const handleNavAction = async (action) => {
    if (isDesktop && webviewRef.current) {
      if (action === 'back' && webviewRef.current.canGoBack()) webviewRef.current.goBack();
      if (action === 'forward' && webviewRef.current.canGoForward()) webviewRef.current.goForward();
      if (action === 'reload') webviewRef.current.reload();
      return;
    }
    await executeInteraction({ action });
  };

  const activeSrc = liveFrame || screenshotUrl;

  return (
    <div className="card chrome-window" style={{ padding: 0, overflow: 'hidden', border: '1px solid #cbd5e1', boxShadow: '0 10px 25px -5px rgba(0,0,0,0.1)' }}>

      {/* 1. Chrome Titlebar & Window Controls */}
      <div className="chrome-titlebar" style={{ backgroundColor: '#dfe1e5', padding: '6px 12px 0 12px', display: 'flex', alignItems: 'center', gap: '12px', borderBottom: '1px solid #c7c7c7' }}>
        {/* macOS Traffic Light Buttons */}
        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          <div style={{ width: 12, height: 12, borderRadius: '50%', backgroundColor: '#ff5f56', border: '1px solid #e0443e' }} />
          <div style={{ width: 12, height: 12, borderRadius: '50%', backgroundColor: '#ffbd2e', border: '1px solid #dea123' }} />
          <div style={{ width: 12, height: 12, borderRadius: '50%', backgroundColor: '#27c93f', border: '1px solid #1aab29' }} />
        </div>

        {/* Chrome Active Browser Tab */}
        <div style={{ flex: 1, display: 'flex', alignItems: 'center' }}>
          <div style={{
            backgroundColor: '#ffffff',
            padding: '5px 14px',
            borderRadius: '8px 8px 0 0',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '0.8rem',
            fontWeight: '500',
            color: '#202124',
            maxWidth: '240px',
            boxShadow: '0 -1px 3px rgba(0,0,0,0.05)'
          }}>
            <Globe size={13} color="#1a73e8" />
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{getTabTitle()}</span>
            <X size={12} style={{ color: '#5f6368', cursor: 'pointer', marginLeft: 'auto' }} />
          </div>
          <button style={{ background: 'none', border: 'none', padding: '4px 8px', cursor: 'pointer', color: '#5f6368' }}>
            <Plus size={14} />
          </button>
        </div>
      </div>

      {/* 2. Chrome Navigation Toolbar & Address Bar */}
      <div className="chrome-toolbar" style={{ backgroundColor: '#ffffff', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '8px', borderBottom: '1px solid #e2e8f0', flexWrap: 'wrap' }}>
        <button
          type="button"
          onClick={() => handleNavAction('back')}
          disabled={isSending}
          title="Back"
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '4px', borderRadius: '50%', color: '#5f6368' }}
        >
          <ArrowLeft size={16} />
        </button>
        <button
          type="button"
          onClick={() => handleNavAction('forward')}
          disabled={isSending}
          title="Forward"
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '4px', borderRadius: '50%', color: '#5f6368' }}
        >
          <ArrowRight size={16} />
        </button>
        <button
          type="button"
          onClick={() => handleNavAction('reload')}
          disabled={isSending}
          title="Reload page"
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '4px', borderRadius: '50%', color: '#5f6368' }}
        >
          <RotateCw size={14} />
        </button>
        <button
          type="button"
          onClick={() => handleNavSubmit({ preventDefault: () => { } })}
          disabled={isSending}
          title="Home"
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '4px', borderRadius: '50%', color: '#5f6368' }}
        >
          <Home size={14} />
        </button>

        {/* Chrome Address Bar Box */}
        <form onSubmit={handleNavSubmit} style={{
          flex: 1,
          minWidth: '180px',
          display: 'flex',
          alignItems: 'center',
          backgroundColor: '#f1f3f4',
          borderRadius: '20px',
          padding: '4px 12px',
          border: '1px solid transparent',
          transition: 'all 0.2s ease'
        }}>
          <Lock size={13} style={{ marginRight: '8px', color: '#1a73e8' }} title="Connection is secure" />
          <input
            type="text"
            value={navUrl}
            onChange={(e) => setNavUrl(e.target.value)}
            placeholder="Search Google or type a URL"
            style={{
              width: '100%',
              background: 'transparent',
              border: 'none',
              fontSize: '0.85rem',
              color: '#202124',
              outline: 'none',
              fontFamily: 'Inter, system-ui, sans-serif'
            }}
          />
        </form>

        {/* Real-time Status Badge */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          padding: '3px 10px',
          borderRadius: '12px',
          backgroundColor: statusBadge.bg,
          border: `1px solid ${statusBadge.border}`,
          fontSize: '0.72rem',
          fontWeight: '500',
          color: statusBadge.color,
          whiteSpace: 'nowrap',
          userSelect: 'none'
        }}>
          <span style={{
            width: 7,
            height: 7,
            borderRadius: '50%',
            backgroundColor: statusBadge.color,
            boxShadow: `0 0 6px ${statusBadge.color}`,
            display: 'inline-block',
            animation: statusBadge.pulse ? 'pulse 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite' : 'none'
          }} />
          <span>{statusBadge.text}</span>
        </div>

        {/* View Mode Toggle: Real Desktop Chrome (noVNC) vs Fast Stream */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          backgroundColor: '#f1f5f9',
          borderRadius: '8px',
          padding: '2px',
          border: '1px solid #e2e8f0',
          gap: '2px'
        }}>
          <button
            type="button"
            onClick={() => setViewMode('vnc')}
            style={{
              padding: '3px 8px',
              borderRadius: '6px',
              fontSize: '0.72rem',
              fontWeight: 600,
              border: 'none',
              cursor: 'pointer',
              backgroundColor: viewMode === 'vnc' ? '#ffffff' : 'transparent',
              color: viewMode === 'vnc' ? '#2563eb' : '#64748b',
              boxShadow: viewMode === 'vnc' ? '0 1px 2px rgba(0,0,0,0.06)' : 'none',
              transition: 'all 0.15s ease'
            }}
            title="Real Embedded Google Chrome Session with Native UI, Hardware Input, and Context Menus"
          >
            🖥️ Native Chrome
          </button>
          <button
            type="button"
            onClick={() => setViewMode('stream')}
            style={{
              padding: '3px 8px',
              borderRadius: '6px',
              fontSize: '0.72rem',
              fontWeight: 600,
              border: 'none',
              cursor: 'pointer',
              backgroundColor: viewMode === 'stream' ? '#ffffff' : 'transparent',
              color: viewMode === 'stream' ? '#2563eb' : '#64748b',
              boxShadow: viewMode === 'stream' ? '0 1px 2px rgba(0,0,0,0.06)' : 'none',
              transition: 'all 0.15s ease'
            }}
            title="Fast Lightweight Compositor Stream"
          >
            ⚡ Stream
          </button>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.75rem', color: '#5f6368' }}>
          <ShieldCheck size={16} color="#0f9d58" title="Playwright Guard Active" />
        </div>
      </div>

      {/* 3. Real Chrome Page Viewport with Mouse Wheel Scrolling & Human-in-the-Loop Drag */}
      <div
        ref={containerRef}
        tabIndex={0}
        onKeyDown={handleContainerKeyDown}
        onWheel={handleWheel}
        className="preview-container"
        style={{
          position: 'relative',
          cursor: isDragging ? 'grabbing' : 'crosshair',
          outline: 'none',
          backgroundColor: '#ffffff',
          minHeight: '420px',
          overflow: 'hidden',
          userSelect: 'none'
        }}
        title="Human-in-the-loop: Click, Drag Sliders, Scroll, or Type directly to solve CAPTCHAs & interact"
      >
        {isDesktop ? (
          <webview
            ref={webviewRef}
            src={currentUrl || 'about:blank'}
            className="embedded-browser-view"
            allowpopups="false"
            title="Embedded Chromium browser"
            onDidNavigate={(event) => setNavUrl(event.url)}
            onDidNavigateInPage={(event) => setNavUrl(event.url)}
          />
        ) : viewMode === 'vnc' ? (
          <div style={{ width: '100%', height: '100%', minHeight: '520px', position: 'relative' }}>
            <iframe
              src="/vnc/vnc_lite.html?autoconnect=true&resize=scale&reconnect=true&path=websockify"
              title="Real Google Chrome Embedded Desktop Session"
              allow="clipboard-read; clipboard-write"
              style={{
                width: '100%',
                height: '100%',
                minHeight: '520px',
                border: 'none',
                display: 'block',
                backgroundColor: '#0f172a'
              }}
            />
          </div>
        ) : displayedSrc ? (
          <>
            <img
              ref={imageRef}
              src={displayedSrc}
              alt=""
              className="screenshot-img"
              draggable={false}
              onMouseDown={handleMouseDown}
              onDoubleClick={handleDoubleClick}
              style={{
                width: '100%',
                height: 'auto',
                display: 'block',
                pointerEvents: 'auto',
                userSelect: 'none',
                WebkitUserDrag: 'none',
                cursor: isDragging ? 'grabbing' : 'crosshair'
              }}
            />
            {lastClick && (
              <div
                style={{
                  position: 'absolute',
                  left: lastClick.x - 12,
                  top: lastClick.y - 12,
                  width: 24,
                  height: 24,
                  borderRadius: '50%',
                  backgroundColor: 'rgba(37, 99, 235, 0.5)',
                  border: '2px solid #2563eb',
                  pointerEvents: 'none',
                  animation: 'ping 1s cubic-bezier(0, 0, 0.2, 1) infinite'
                }}
              />
            )}
            {/* Live Compositor Stream Telemetry Banner */}
            <div style={{
              position: 'absolute',
              bottom: '10px',
              right: '12px',
              zIndex: 10,
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '3px 8px',
              borderRadius: '6px',
              backgroundColor: 'rgba(15, 23, 42, 0.75)',
              backdropFilter: 'blur(4px)',
              fontSize: '0.68rem',
              color: '#e2e8f0',
              pointerEvents: 'none',
              boxShadow: '0 2px 8px rgba(0,0,0,0.2)'
            }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: '#22c55e' }} />
              <span>Direct Chrome Stream Active</span>
            </div>
          </>
        ) : (
          <div style={{ color: '#64748b', textAlign: 'center', padding: '3.5rem' }}>
            <Monitor size={52} style={{ opacity: 0.3, marginBottom: '1rem', color: '#2563eb' }} />
            <p style={{ fontWeight: '600', color: '#1e293b' }}>Google Chrome Browser Initializing...</p>
            <p style={{ fontSize: '0.8rem', color: '#64748b', marginTop: '0.4rem' }}>Live browser stream active. Ready for interaction.</p>
          </div>
        )}
      </div>

    </div>
  );
}
