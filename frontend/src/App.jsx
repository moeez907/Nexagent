import React, { useState, useEffect, useRef } from 'react';
import Navbar from './components/Navbar';
import TaskInput from './components/TaskInput';
import TaskProgress from './components/TaskProgress';
import BrowserPreview from './components/BrowserPreview';
import ResultView from './components/ResultView';
import TaskHistory from './components/TaskHistory';
import AuthScreen from './components/AuthScreen';
import HomePage from './components/HomePage';
import { User, Sparkles, Activity, TrendingUp, Compass, Newspaper, Search, ChevronDown, Download, Code } from 'lucide-react';

import {
  createTask,
  fetchTasks,
  fetchTaskDetails,
  clearAllTasks,
  deleteTask,
  submitHumanResponse,
  pauseTask,
  resumeTask,
  sendBrowserInteraction,
  connectTaskWebSocket
} from './services/api';
import { fetchCurrentUser, logout } from './services/api';

export default function App() {
  const [activeTaskId, setActiveTaskId] = useState(() => {
    try {
      return localStorage.getItem('nexagent_active_task_id') || null;
    } catch {
      return null;
    }
  });
  const [sessionTaskIds, setSessionTaskIds] = useState([]);
  const [tasksData, setTasksData] = useState({});
  const [taskState, setTaskState] = useState(null);
  const [events, setEvents] = useState([]);
  const [screenshotUrl, setScreenshotUrl] = useState('');
  const [currentUrl, setCurrentUrl] = useState('');
  const [result, setResult] = useState(null);
  const [pendingIntervention, setPendingIntervention] = useState(null);
  const [historyTasks, setHistoryTasks] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isHumanResponseSubmitting, setIsHumanResponseSubmitting] = useState(false);
  const [user, setUser] = useState(undefined);
  const [viewMode, setViewMode] = useState(() => {
    try {
      return localStorage.getItem('nexagent_view_mode') || 'home';
    } catch {
      return 'home';
    }
  });
  const [showAuthScreen, setShowAuthScreen] = useState(false);

  // Sync viewMode to localStorage
  useEffect(() => {
    try {
      if (viewMode) {
        localStorage.setItem('nexagent_view_mode', viewMode);
      }
    } catch {}
  }, [viewMode]);

  // Sync activeTaskId to localStorage
  useEffect(() => {
    try {
      if (activeTaskId) {
        localStorage.setItem('nexagent_active_task_id', activeTaskId);
      } else {
        localStorage.removeItem('nexagent_active_task_id');
      }
    } catch {}
  }, [activeTaskId]);
  const pendingMissionRef = useRef(null);
  const activeTaskRef = useRef(null);
  const wsRef = useRef(null);
  const humanResponseSubmittingRef = useRef(false);
  const liveInterventionRef = useRef(false);
  const interventionTimestampRef = useRef('');
  const messagesEndRef = useRef(null);
  const scrollContainerRef = useRef(null);
  const isAtBottomRef = useRef(true);
  const [showScrollBottomBtn, setShowScrollBottomBtn] = useState(false);

  const scrollToBottom = (behavior = 'smooth') => {
    messagesEndRef.current?.scrollIntoView({ behavior, block: 'end' });
  };

  const handleScroll = (e) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    const isAtBottom = distanceFromBottom <= 80;
    isAtBottomRef.current = isAtBottom;
    setShowScrollBottomBtn(!isAtBottom && scrollHeight > clientHeight + 100);
  };

  const handleManualScrollToBottom = () => {
    isAtBottomRef.current = true;
    setShowScrollBottomBtn(false);
    scrollToBottom('smooth');
  };

  useEffect(() => {
    // Only auto-scroll down if the user is already at or near the bottom
    // If the user has scrolled up to inspect previous steps/content, don't force them down
    if (activeTaskId && isAtBottomRef.current) {
      const timer = setTimeout(() => {
        scrollToBottom('smooth');
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [events?.length, taskState?.status, result, pendingIntervention, sessionTaskIds?.length]);

  const activeTask = activeTaskId ? historyTasks.find((task) => task.id === activeTaskId || task.active_task_id === activeTaskId || (task.session_task_ids && task.session_task_ids.includes(activeTaskId))) : null;

  const resetWorkspace = () => {
    setActiveTaskId(null);
    setSessionTaskIds([]);
    setTasksData({});
    setTaskState(null);
    setEvents([]);
    setScreenshotUrl('');
    setCurrentUrl('');
    setResult(null);
    setPendingIntervention(null);
    liveInterventionRef.current = false;
    interventionTimestampRef.current = '';
    setHistoryTasks([]);
    setIsLoading(false);
    humanResponseSubmittingRef.current = false;
    setIsHumanResponseSubmitting(false);
    isAtBottomRef.current = true;
    setShowScrollBottomBtn(false);
  };

  // Sync active task data into tasksData map
  useEffect(() => {
    if (!activeTaskId) return;
    setTasksData((prev) => ({
      ...prev,
      [activeTaskId]: {
        ...(prev[activeTaskId] || {}),
        id: activeTaskId,
        goal: taskState?.goal || prev[activeTaskId]?.goal || activeTask?.goal,
        status: taskState?.status || prev[activeTaskId]?.status,
        events: events,
        result: result,
        pendingIntervention: pendingIntervention
      }
    }));
  }, [activeTaskId, taskState?.status, taskState?.goal, events, result, pendingIntervention]);

  async function loadTaskDetails(taskId) {
    try {
      const details = await fetchTaskDetails(taskId);
      if (details) {
        setSessionTaskIds((prev) => (prev.includes(taskId) ? prev : [...prev, taskId]));
        setTasksData((prev) => ({
          ...prev,
          [taskId]: {
            ...(prev[taskId] || {}),
            id: details.id,
            goal: details.goal,
            status: details.status,
            events: details.events || [],
            result: details.result || null,
            pendingIntervention: details.pending_intervention || null
          }
        }));
      }
      if (activeTaskRef.current !== taskId) return;
      setTaskState({
        id: details.id,
        goal: details.goal,
        status: details.status
      });
      if (details.current_url) {
        setCurrentUrl(details.current_url);
      }
      setEvents(details.events || []);
      if (details.events && details.events.length > 0) {
        const screenshotEvents = details.events.filter((e) => e.screenshot_path);
        if (screenshotEvents.length > 0) {
          const lastScreenshot = screenshotEvents[screenshotEvents.length - 1];
          const filename = lastScreenshot.screenshot_path.split(/[\\/]/).pop();
          setScreenshotUrl((prev) => (prev && prev.startsWith('data:') ? prev : `/api/tasks/${taskId}/screenshot/${filename}?t=${Date.now()}`));
        }
      } else {
        // If there are no completed step events yet, fetch the active browser live frame
        fetch(`/api/tasks/${taskId}/live_frame`)
          .then((r) => (r.ok ? r.json() : null))
          .then((frame) => {
            if (frame && activeTaskRef.current === taskId) {
              if (frame.frame_data) setScreenshotUrl((prev) => prev || frame.frame_data);
              if (frame.url) setCurrentUrl((prev) => prev || frame.url);
            }
          })
          .catch(() => {});
      }
      // Do not let the initial request race overwrite a live completion event.
      if (details.result) {
        setResult(details.result);
      }
      const terminalStatus = ['COMPLETED', 'FAILED'].includes(details.status);
      if (terminalStatus) {
        humanResponseSubmittingRef.current = false;
        setIsHumanResponseSubmitting(false);
        setPendingIntervention(null);
      } else if (details.status === 'RUNNING' && humanResponseSubmittingRef.current) {
        humanResponseSubmittingRef.current = false;
        setIsHumanResponseSubmitting(false);
        setPendingIntervention(null);
        liveInterventionRef.current = false;
      } else if (details.pending_intervention && !liveInterventionRef.current) {
        const createdAt = details.pending_intervention.created_at || '';
        if (!interventionTimestampRef.current || createdAt >= interventionTimestampRef.current) {
          humanResponseSubmittingRef.current = false;
          setIsHumanResponseSubmitting(false);
          interventionTimestampRef.current = createdAt;
          setPendingIntervention(details.pending_intervention || null);
        }
      }
    } catch (e) {
      console.error('Error loading task details:', e);
    }
  }

  async function loadHistory(isCurrentAccount = () => true) {
    try {
      const tasks = await fetchTasks();
      if (isCurrentAccount()) {
        setHistoryTasks(tasks);
        let currentActive = activeTaskId;
        try {
          if (!currentActive) currentActive = localStorage.getItem('nexagent_active_task_id');
        } catch {}
        if (currentActive) {
          const session = tasks.find(
            (t) => t.id === currentActive || t.active_task_id === currentActive || (t.session_task_ids && t.session_task_ids.includes(currentActive))
          );
          if (session && session.session_task_ids && session.session_task_ids.length > 0) {
            setSessionTaskIds(session.session_task_ids);
            const targetActive = session.active_task_id || session.id;
            setActiveTaskId(targetActive);
            session.session_task_ids.forEach((tid) => loadTaskDetails(tid));
          } else {
            setSessionTaskIds([currentActive]);
            loadTaskDetails(currentActive);
          }
        }
      }
    } catch (e) {
      console.error('Error fetching task history:', e);
    }
  }

  function handleWebSocketMessage(message) {
    const currentId = message.task_id || activeTaskRef.current;
    if (message.task_id && message.task_id !== activeTaskRef.current) return;
    const { event_type, data } = message;

    if (event_type === 'BROWSER_FRAME') {
      if (data?.frame_data) setScreenshotUrl(data.frame_data);
    } else if (event_type === 'EVENT_REPLAY') {
      const replayEvents = data?.events || [];
      replayEvents.forEach((replayedMessage) => handleWebSocketMessage(replayedMessage));
    } else if (event_type === 'STATUS_CHANGE' || event_type === 'TASK_PAUSED' || event_type === 'TASK_RESUMED') {
      const nextStatus = data.status || (event_type === 'TASK_PAUSED' ? 'PAUSED' : 'RUNNING');
      setTaskState((prev) => prev ? { ...prev, status: nextStatus } : null);
      if (['COMPLETED', 'FAILED'].includes(nextStatus)
        || (nextStatus === 'RUNNING' && humanResponseSubmittingRef.current)) {
        humanResponseSubmittingRef.current = false;
        setIsHumanResponseSubmitting(false);
        setPendingIntervention(null);
        liveInterventionRef.current = false;
        interventionTimestampRef.current = '';
      }
      if (data.url) setCurrentUrl(data.url);
      loadHistory();
    } else if (event_type === 'BROWSER_OBSERVED') {
      if (data.url) setCurrentUrl(data.url);
      if (data.screenshot_path) {
        // Bust browser cache by appending timestamp
        const filename = data.screenshot_path.split(/[\\/]/).pop();
        setScreenshotUrl(`/api/tasks/${currentId}/screenshot/${filename}?t=${Date.now()}`);
      }
    } else if (event_type === 'ACTION_PLANNED') {
      setEvents((prev) => [
        ...prev,
        {
          step: data.step,
          type: data.action,
          intent: data.intent,
          ordered_steps: data.ordered_steps,
          current_requirement: data.current_requirement,
          completed_subtasks: data.completed_subtasks,
          success: true
        }
      ]);
    } else if (event_type === 'SUBTASK_COMPLETED') {
      setEvents((prev) => [
        ...prev,
        {
          step: data.step,
          type: 'SUBTASK_COMPLETED',
          title: data.title,
          summary: data.summary,
          data: data.data,
          completed_subtasks: data.completed_subtasks || [],
          ordered_steps: data.ordered_steps || [],
          success: true
        }
      ]);
    } else if (event_type === 'VALIDATION_FAILED' || event_type === 'ACTION_FAILED') {
      setEvents((prev) => [
        ...prev,
        {
          step: data.step,
          type: 'ERROR',
          intent: 'Step Execution Error',
          error: data.error,
          success: false
        }
      ]);
    } else if (event_type === 'CAPTCHA_DETECTED' || event_type === 'ACCOUNT_LOGIN_REQUIRED') {
      if (data.url) {
        setCurrentUrl(data.url);
      }
      setPendingIntervention({
        intervention_type: event_type === 'CAPTCHA_DETECTED' ? 'CAPTCHA' : 'ACCOUNT_LOGIN_REQUIRED',
        prompt: data.prompt || data.message || 'Please complete account login in the browser, then continue.'
      });
    } else if (event_type === 'FORM_INPUT_REQUIRED') {
      const createdAt = data.created_at || '';
      if (interventionTimestampRef.current && createdAt && createdAt < interventionTimestampRef.current) return;
      humanResponseSubmittingRef.current = false;
      setIsHumanResponseSubmitting(false);
      interventionTimestampRef.current = createdAt;
      liveInterventionRef.current = true;
      setPendingIntervention({
        id: data.intervention_id,
        created_at: createdAt,
        intervention_type: 'FORM_INPUT_REQUIRED',
        prompt: data.prompt || 'Please provide the required information to continue.',
        fields: data.fields || [],
        active_field: data.active_field || data.fields?.[0],
        suggested_value: data.suggested_value || ''
      });
    } else if (event_type === 'FILE_UPLOAD_REQUIRED') {
      humanResponseSubmittingRef.current = false;
      setIsHumanResponseSubmitting(false);
      interventionTimestampRef.current = data.created_at || '';
      liveInterventionRef.current = true;
      setPendingIntervention({
        intervention_type: 'FILE_UPLOAD_REQUIRED',
        prompt: data.prompt || 'Please upload the required file, then continue.',
        field: data.field || null,
        upload_mode: data.upload_mode || 'file'
      });
    } else if (event_type === 'TASK_COMPLETED' || event_type === 'TASK_FAILED') {
      liveInterventionRef.current = false;
      interventionTimestampRef.current = '';
      const finalStatus = event_type === 'TASK_COMPLETED' ? 'COMPLETED' : 'FAILED';
      setTaskState((prev) => prev ? { ...prev, status: finalStatus } : { id: activeTaskId, status: finalStatus });
      setResult(data || { success: finalStatus === 'COMPLETED' });
      // The REST record is the durable source of truth when the websocket
      // payload arrives before the database request finishes.
      fetchTaskDetails(activeTaskId)
        .then((details) => {
          if (details.result) setResult(details.result);
        })
        .catch((error) => console.error('Error loading completed task result:', error));
      loadHistory();
    }
  }

  // Load user on mount
  useEffect(() => {
    fetchCurrentUser()
      .then((currUser) => {
        setUser(currUser);
        if (!currUser) {
          setViewMode('home');
          try {
            localStorage.removeItem('nexagent_view_mode');
            localStorage.removeItem('nexagent_active_task_id');
          } catch {}
        }
      })
      .catch(() => {
        setUser(null);
        setViewMode('home');
      });
  }, []);

  const initialUserMountRef = useRef(true);
  useEffect(() => {
    if (initialUserMountRef.current) {
      // First mount / page reload: preserve activeTaskId and viewMode from localStorage
      initialUserMountRef.current = false;
    } else {
      // User switched or logged out
      resetWorkspace();
    }

    if (user && (user.guest || user.email)) {
      let isCurrentAccount = true;
      loadHistory(() => isCurrentAccount);
      return () => {
        isCurrentAccount = false;
      };
    }
    return undefined;
  }, [user?.id, user?.email]);

  useEffect(() => {
    if (!user?.guest) return undefined;
    const closeGuestSession = () => navigator.sendBeacon('/api/auth/guest/close', '');
    window.addEventListener('beforeunload', closeGuestSession);
    return () => window.removeEventListener('beforeunload', closeGuestSession);
  }, [user]);

  // Connect WebSocket when activeTaskId changes
  useEffect(() => {
    if (!activeTaskId) return;
    activeTaskRef.current = activeTaskId;
    liveInterventionRef.current = false;
    interventionTimestampRef.current = '';

    // Fetch initial details
    loadTaskDetails(activeTaskId);

    const pollTimer = window.setInterval(() => {
      loadTaskDetails(activeTaskId);
    }, 2000);

    const ws = connectTaskWebSocket(activeTaskId, (message) => {
      handleWebSocketMessage(message);
    });
    wsRef.current = ws;

    return () => {
      if (activeTaskRef.current === activeTaskId) activeTaskRef.current = null;
      window.clearInterval(pollTimer);
      ws.close();
      wsRef.current = null;
    };
  }, [activeTaskId]);

  const handleStartTask = async (goal, file = null) => {
    setIsLoading(true);
    const parentTaskId = activeTaskId;
    try {
      const res = await createTask(goal, file, parentTaskId);
      const newTaskId = res.task_id;
      setActiveTaskId(newTaskId);
      setSessionTaskIds((prev) => (prev.includes(newTaskId) ? prev : [...prev, newTaskId]));
      setTasksData((prev) => ({
        ...prev,
        [newTaskId]: {
          id: newTaskId,
          goal: goal,
          status: 'PLANNING',
          events: [],
          result: null,
          pendingIntervention: null
        }
      }));
      setTaskState({ id: newTaskId, goal: goal, status: 'PLANNING' });
      setEvents([]);
      setResult(null);
      if (!parentTaskId) {
        setScreenshotUrl('');
        setCurrentUrl('');
      }
      setPendingIntervention(null);
      liveInterventionRef.current = false;
      interventionTimestampRef.current = '';
      humanResponseSubmittingRef.current = false;
      setIsHumanResponseSubmitting(false);
      isAtBottomRef.current = true;
      setShowScrollBottomBtn(false);
      setTimeout(() => scrollToBottom('smooth'), 80);
      await loadHistory();
    } catch (e) {
      alert(`Error starting task: ${e.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleHumanResponse = async (approved, responseData = {}) => {
    await handleHumanRespond(approved, responseData);
  };

  const handleInterventionSubmit = async (text, attachedFile) => {
    let fileText = '';
    let fileName = '';
    if (attachedFile) {
      try {
        fileText = await attachedFile.text();
        fileName = attachedFile.name;
      } catch (err) {
        console.error('Error reading attached file:', err);
      }
    }
    const cleanText = (text || '').trim();
    const replyText = cleanText || (fileName ? `Attached file: ${fileName}` : '');
    await handleHumanResponse(true, {
      text: replyText,
      file_text: fileText,
      file_name: fileName,
    });
  };

  const handlePauseTask = async () => {
    if (!activeTaskId) return;
    try {
      await pauseTask(activeTaskId);
      setTaskState((prev) => prev ? { ...prev, status: 'PAUSED' } : null);
    } catch (e) {
      alert(`Error pausing task: ${e.message}`);
    }
  };

  const handleResumeTask = async () => {
    if (!activeTaskId) return;
    try {
      await resumeTask(activeTaskId);
      setTaskState((prev) => prev ? { ...prev, status: 'RUNNING' } : null);
    } catch (e) {
      alert(`Error resuming task: ${e.message}`);
    }
  };

  const handleBrowserInteract = async (payload) => {
    if (!activeTaskId) return null;
    if (['COMPLETED', 'FAILED', 'CANCELLED'].includes(taskState?.status)) return null;
    // Fast path: send directly via WebSocket for instant, non-blocking response (<2ms)
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.send(JSON.stringify({ type: 'INTERACTION', payload }));
        return { status: 'sent_ws' };
      } catch (err) {
        // fall back to HTTP
      }
    }
    // HTTP Fallback
    try {
      const res = await sendBrowserInteraction(activeTaskId, payload);
      if (res?.frame_data) {
        setScreenshotUrl(res.frame_data);
      } else if (res?.screenshot_path) {
        const filename = res.screenshot_path.split(/[\\/]/).pop();
        setScreenshotUrl(`/api/tasks/${activeTaskId}/screenshot/${filename}?t=${Date.now()}`);
      }
      if (res?.url) setCurrentUrl(res.url);
      return res;
    } catch (e) {
      return null;
    }
  };

  const handleHumanRespond = async (approved, responseData = {}) => {
    if (!activeTaskId) return;
    if (humanResponseSubmittingRef.current) return;
    humanResponseSubmittingRef.current = true;
    setIsHumanResponseSubmitting(true);
    // Immediately dismiss intervention box on reply/action
    setPendingIntervention(null);
    liveInterventionRef.current = false;
    try {
      await submitHumanResponse(activeTaskId, approved, responseData);
      humanResponseSubmittingRef.current = false;
      setIsHumanResponseSubmitting(false);
    } catch (e) {
      humanResponseSubmittingRef.current = false;
      setIsHumanResponseSubmitting(false);
      alert(`Error submitting human resolution: ${e.message}`);
    }
  };

  const handleLogout = async () => {
    try {
      if (user && !user.guest) await logout();
    } catch (e) {
      console.error('Logout error:', e);
    } finally {
      resetWorkspace();
      setUser(null);
      setViewMode('home');
      try {
        localStorage.removeItem('nexagent_view_mode');
        localStorage.removeItem('nexagent_active_task_id');
      } catch {}
    }
  };

  const handleSelectHistoryTask = (taskOrId) => {
    const taskId = typeof taskOrId === 'object' ? (taskOrId.id || taskOrId.active_task_id) : taskOrId;
    const session = historyTasks.find((t) => t.id === taskId || t.active_task_id === taskId) || (typeof taskOrId === 'object' ? taskOrId : null);
    if (session && session.session_task_ids && session.session_task_ids.length > 0) {
      setSessionTaskIds(session.session_task_ids);
      const targetActive = session.active_task_id || session.id;
      setActiveTaskId(targetActive);
      session.session_task_ids.forEach((tid) => loadTaskDetails(tid));
    } else {
      setActiveTaskId(taskId);
      setSessionTaskIds([taskId]);
      loadTaskDetails(taskId);
    }
    isAtBottomRef.current = true;
    setShowScrollBottomBtn(false);
    setTimeout(() => scrollToBottom('auto'), 50);
  };

  const handleClearHistory = async () => {
    if (!window.confirm("Are you sure you want to delete all task execution history from the database?")) return;
    try {
      await clearAllTasks();
      resetWorkspace();
    } catch (e) {
      alert(`Error clearing task history: ${e.message}`);
    }
  };

  const handleDeleteTask = async (taskId) => {
    try {
      await deleteTask(taskId);
      setHistoryTasks(prev => prev.filter(t => t.id !== taskId));
      setSessionTaskIds(prev => prev.filter(id => id !== taskId));
      setTasksData(prev => {
        const next = { ...prev };
        delete next[taskId];
        return next;
      });
      if (activeTaskId === taskId) {
        setActiveTaskId(null);
        setTaskState(null);
        setEvents([]);
        setResult(null);
        setPendingIntervention(null);
        setScreenshotUrl('');
        setCurrentUrl('');
      }
    } catch (e) {
      alert(`Error deleting task: ${e.message}`);
    }
  };

  const isAgentWorking = activeTaskId && !['COMPLETED', 'FAILED', 'PAUSED'].includes(taskState?.status) && !pendingIntervention;
  const isInputDisabled = isLoading || isHumanResponseSubmitting || isAgentWorking;
  const isInitialState = sessionTaskIds.length === 0 && !activeTaskId;

  if (user === undefined) return <div className="auth-loading">Loading workspace...</div>;

  if (showAuthScreen) {
    return (
      <AuthScreen
        onAuthenticated={(account) => {
          setUser(account);
          setShowAuthScreen(false);
          setViewMode('workspace');
          if (pendingMissionRef.current) {
            const missionToRun = pendingMissionRef.current;
            pendingMissionRef.current = null;
            setTimeout(() => {
              handleStartTask(missionToRun);
            }, 350);
          }
        }}
        onClose={() => setShowAuthScreen(false)}
      />
    );
  }

  if (viewMode === 'home') {
    return (
      <HomePage
        user={user}
        onGetStarted={(goalOrEmail) => {
          // Do not navigate to the chat page without login
          if (!user || user.guest) {
            if (goalOrEmail && typeof goalOrEmail === 'string' && !goalOrEmail.includes('@') && goalOrEmail.trim().length > 3) {
              pendingMissionRef.current = goalOrEmail.trim();
            }
            setShowAuthScreen(true);
            return;
          }
          setViewMode('workspace');
          if (goalOrEmail && typeof goalOrEmail === 'string' && !goalOrEmail.includes('@') && goalOrEmail.trim().length > 3) {
            setTimeout(() => {
              handleStartTask(goalOrEmail.trim());
            }, 300);
          }
        }}
        onSignIn={() => setShowAuthScreen(true)}
        onSelectMission={(missionGoal) => {
          // Do not navigate to the chat page without login
          if (!user || user.guest) {
            pendingMissionRef.current = missionGoal;
            setShowAuthScreen(true);
            return;
          }
          setViewMode('workspace');
          setTimeout(() => {
            handleStartTask(missionGoal);
          }, 300);
        }}
      />
    );
  }

  const handleExportCsv = (res, goal) => {
    const rawData = res?.extracted_data ?? res?.final_data ?? res?.data ?? {};
    let data = rawData;
    if (typeof data === 'string') {
      try { data = JSON.parse(data); } catch { }
    }
    const items = Array.isArray(data) ? data : (data?.items || data?.products || data?.results || []);
    if (!items.length) {
      alert("No extracted tabular products found to export.");
      return;
    }
    const headers = Object.keys(items[0]);
    const rows = items.map(item => headers.map(h => JSON.stringify(item[h] ?? "")).join(","));
    const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `${(goal || "task").slice(0, 30).replace(/[^a-zA-Z0-9]/g, "_")}_products.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleExportJson = (res, goal) => {
    const data = res?.extracted_data ?? res?.final_data ?? res ?? {};
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(data, null, 2));
    const link = document.createElement("a");
    link.setAttribute("href", dataStr);
    link.setAttribute("download", `${(goal || "task").slice(0, 30).replace(/[^a-zA-Z0-9]/g, "_")}_results.json`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };


  return (
    <div className="app-container">
      <Navbar user={user} onLogout={handleLogout} onGoHome={() => setViewMode('home')} />

      <main className={`chat-workspace ${isInitialState ? 'initial-mode' : ''}`}>
        <TaskHistory
          tasks={historyTasks}
          onSelectTask={handleSelectHistoryTask}
          activeTaskId={activeTaskId}
          onClearHistory={handleClearHistory}
          onDeleteTask={handleDeleteTask}
          onNewTask={() => {
            setActiveTaskId(null);
            try {
              localStorage.removeItem('nexagent_active_task_id');
            } catch {}
            setSessionTaskIds([]);
            setTaskState(null);
            setEvents([]);
            setResult(null);
            setPendingIntervention(null);
            setScreenshotUrl('');
            setCurrentUrl('');
          }}
        />

        <section className="conversation-shell" style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
          <div className="conversation-scroll" ref={scrollContainerRef} onScroll={handleScroll} style={{ flex: 1, overflowY: 'auto', padding: '1.25rem 1.5rem' }}>
            {isInitialState && (
              <div className="claude-hero-wrapper">
                {/* Nexagent Brand Logo */}
                <img
                  src="/logo.png"
                  alt="Nexagent"
                  style={{
                    width: 52,
                    height: 52,
                    borderRadius: '13px',
                    objectFit: 'cover',
                    margin: '0 auto 1.15rem',
                    display: 'block',
                    boxShadow: '0 8px 24px -4px rgba(37, 99, 235, 0.25)',
                    border: '1px solid rgba(226, 232, 240, 0.9)'
                  }}
                />

                {/* Nexagent Title */}
                <h1 className="claude-hero-title">
                  Nex<span style={{ background: 'linear-gradient(135deg, #2563eb 0%, #7c3aed 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>agent</span>
                </h1>

                {/* Professional User Greeting */}
                {(() => {
                  const displayName = user?.guest
                    ? 'Guest'
                    : (user?.name || (user?.email ? user.email.split('@')[0] : ''));
                  return (
                    <p className="claude-hero-subtitle" style={{ fontSize: '1.02rem', color: '#475569', fontWeight: 500, margin: '0 auto 1.75rem', textAlign: 'center' }}>
                      Hello, <span style={{ fontWeight: 700, color: '#0f172a' }}>{displayName || 'there'}</span>. How can I assist you today?
                    </p>
                  );
                })()}

                <div className="claude-hero-input-wrapper">
                  <TaskInput
                    onSubmit={handleStartTask}
                    disabled={isInputDisabled}
                    isLoading={isLoading}
                    placeholder="Give me any web task. I will navigate, inspect, extract data, and report findings here."
                    submitLabel="Run Task"
                  />
                </div>

                <div className="claude-suggestions">
                  <button
                    type="button"
                    className="claude-suggestion-card"
                    onClick={() => handleStartTask("Search the latest AI breakthroughs on TechCrunch and summarize findings")}
                  >
                    <div className="claude-suggestion-icon"><TrendingUp size={15} /></div>
                    <span className="claude-suggestion-text">Latest AI breakthroughs on TechCrunch</span>
                  </button>

                  <button
                    type="button"
                    className="claude-suggestion-card"
                    onClick={() => handleStartTask("Find top trending open-source AI repositories on GitHub")}
                  >
                    <div className="claude-suggestion-icon"><Compass size={15} /></div>
                    <span className="claude-suggestion-text">Top trending AI repos on GitHub</span>
                  </button>

                  <button
                    type="button"
                    className="claude-suggestion-card"
                    onClick={() => handleStartTask("Search top global news headlines on BBC News")}
                  >
                    <div className="claude-suggestion-icon"><Newspaper size={15} /></div>
                    <span className="claude-suggestion-text">Top global news headlines on BBC</span>
                  </button>

                  <button
                    type="button"
                    className="claude-suggestion-card"
                    onClick={() => handleStartTask("Search and compare current prices for MacBook Air M3 on Amazon")}
                  >
                    <div className="claude-suggestion-icon"><Search size={15} /></div>
                    <span className="claude-suggestion-text">Compare MacBook Air M3 prices</span>
                  </button>
                </div>
              </div>
            )}

            {!isInitialState && sessionTaskIds.map((tid, idx) => {
              const tData = tasksData[tid] || {};
              const isCurrent = tid === activeTaskId;
              const displayGoal = tData.goal || (isCurrent ? taskState?.goal : activeTask?.goal);
              const displayStatus = isCurrent ? (taskState?.status || tData.status) : tData.status;
              const displayEvents = isCurrent ? events : (tData.events || []);
              const displayResult = isCurrent ? result : tData.result;
              const displayIntervention = isCurrent ? pendingIntervention : null;
              const isCompleted = displayStatus === 'COMPLETED';

              return (
                <div key={tid || idx} className="task-turn-block" style={{ marginBottom: '1.75rem', display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>

                  {/* Task Header: Status pill, elapsed, steps finished, and Export CSV / JSON buttons */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.55rem', flexWrap: 'wrap' }}>
                      <span style={{
                        backgroundColor: isCompleted ? '#dcfce7' : '#dbeafe',
                        color: isCompleted ? '#166534' : '#1d4ed8',
                        fontSize: '0.72rem',
                        fontWeight: 800,
                        padding: '0.2rem 0.6rem',
                        borderRadius: '5px',
                        letterSpacing: '0.04em',
                        textTransform: 'uppercase'
                      }}>
                        {displayStatus || 'RUNNING'}
                      </span>
                    </div>

                    {/* Export Buttons */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <button
                        type="button"
                        onClick={() => handleExportCsv(displayResult, displayGoal)}
                        style={{
                          backgroundColor: '#ffffff',
                          border: '1px solid #e2e8f0',
                          borderRadius: '8px',
                          padding: '0.35rem 0.75rem',
                          fontSize: '0.76rem',
                          fontWeight: 600,
                          color: '#334155',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.4rem',
                          cursor: 'pointer',
                          boxShadow: '0 1px 2px rgba(0,0,0,0.02)'
                        }}
                      >
                        <Download size={13} />
                        <span>Export CSV</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => handleExportJson(displayResult, displayGoal)}
                        style={{
                          backgroundColor: '#ffffff',
                          border: '1px solid #e2e8f0',
                          borderRadius: '8px',
                          padding: '0.35rem 0.75rem',
                          fontSize: '0.76rem',
                          fontWeight: 600,
                          color: '#334155',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.4rem',
                          cursor: 'pointer',
                          boxShadow: '0 1px 2px rgba(0,0,0,0.02)'
                        }}
                      >
                        <Code size={13} />
                        <span>JSON</span>
                      </button>
                    </div>
                  </div>

                  {/* Task Prompt Title */}
                  <h2 style={{
                    fontSize: '1.2rem',
                    fontWeight: 800,
                    color: '#0f172a',
                    margin: '0.2rem 0 0.5rem 0',
                    letterSpacing: '-0.015em'
                  }}>
                    {displayGoal}
                  </h2>

                  {/* Execution Steps Timeline */}
                  <TaskProgress
                    taskState={{ id: tid, goal: displayGoal, status: displayStatus }}
                    events={displayEvents}
                    onPauseTask={handlePauseTask}
                    onResumeTask={handleResumeTask}
                  />

                  {/* Human Intervention Box */}
                  {displayIntervention && (
                    <div className="chat-message intervention-message">
                      <div className="message-avatar warning-avatar">!</div>
                      <div className="intervention-content">
                        <strong style={{ fontSize: '0.98rem', color: displayIntervention.intervention_type === 'ACCOUNT_LOGIN_REQUIRED' ? '#1d4ed8' : '#0f172a' }}>
                          {displayIntervention.intervention_type === 'ACCOUNT_LOGIN_REQUIRED'
                            ? 'Google Account Sign-In Required'
                            : displayIntervention.intervention_type === 'CAPTCHA'
                            ? 'Human Verification / CAPTCHA Detected'
                            : 'Action needed from you'}
                        </strong>
                        <p style={{ marginTop: '0.3rem', marginBottom: '0.5rem', lineHeight: '1.45' }}>
                          {displayIntervention.prompt || 'Please complete the required browser verification.'}
                        </p>
                        {displayIntervention.intervention_type === 'ACCOUNT_LOGIN_REQUIRED' && (
                          <div style={{ fontSize: '0.84rem', color: '#1e3a8a', background: '#eff6ff', padding: '0.65rem 0.85rem', borderRadius: '7px', border: '1px solid #bfdbfe', marginBottom: '0.65rem' }}>
                            Sign in to your Google Account directly in the <strong>Live Browser Preview</strong> on the right. Once signed in, click <strong>Continue (Signed In)</strong> below to proceed with your task.
                          </div>
                        )}
                        <div className="inline-actions">
                          {displayIntervention.intervention_type !== 'FORM_INPUT_REQUIRED' && (
                            displayIntervention.intervention_type !== 'FILE_UPLOAD_REQUIRED' && (
                              <button className="btn-approve" disabled={isHumanResponseSubmitting} onClick={() => handleHumanResponse(true)}>
                                {isHumanResponseSubmitting ? 'Processing...' : (displayIntervention.intervention_type === 'ACCOUNT_LOGIN_REQUIRED' ? 'Continue (Signed In)' : 'Continue')}
                              </button>
                            )
                          )}
                          {displayIntervention.intervention_type === 'FILE_UPLOAD_REQUIRED' && (
                            <>
                              <button className="btn-approve" disabled={isHumanResponseSubmitting} onClick={() => handleHumanResponse(true)}>{isHumanResponseSubmitting ? 'Processing...' : 'Continue'}</button>
                            </>
                          )}
                          {displayIntervention.intervention_type === 'FORM_INPUT_REQUIRED' && displayIntervention.suggested_value && (
                            <button className="btn-approve" disabled={isHumanResponseSubmitting} onClick={() => handleHumanResponse(true, { text: displayIntervention.suggested_value })}>{isHumanResponseSubmitting ? 'Processing...' : 'Fill this value'}</button>
                          )}
                          <button className="btn-reject" disabled={isHumanResponseSubmitting} onClick={() => handleHumanResponse(false)}>Stop task</button>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Result View: Executive Market Analysis & Dynamic Extracted Product Cards */}
                  {displayResult && <ResultView result={displayResult} />}
                </div>
              );
            })}
            <div ref={messagesEndRef} style={{ height: '1px' }} />
          </div>

          {showScrollBottomBtn && (
            <button
              onClick={handleManualScrollToBottom}
              className="scroll-to-bottom-btn"
              title="Scroll to bottom"
              aria-label="Scroll to bottom"
            >
              <ChevronDown size={18} />
            </button>
          )}

          {!isInitialState && (
            <div className="bottom-composer-wrapper" style={{ padding: '0.85rem 1.5rem', backgroundColor: '#ffffff', borderTop: '1px solid #e2e8f0' }}>
              <TaskInput
                onSubmit={pendingIntervention?.intervention_type === 'FORM_INPUT_REQUIRED'
                  ? handleInterventionSubmit
                  : handleStartTask}
                disabled={isInputDisabled}
                isLoading={isLoading || isHumanResponseSubmitting}
                placeholder={isAgentWorking
                  ? 'AI is working on the task...'
                  : (pendingIntervention?.intervention_type === 'FORM_INPUT_REQUIRED'
                    ? `Reply with ${pendingIntervention.active_field?.label || 'the required information'}`
                    : 'Ask a follow-up question or enter your next instruction...')}
                submitLabel={pendingIntervention?.intervention_type === 'FORM_INPUT_REQUIRED' ? 'Reply' : (isAgentWorking ? 'Working...' : 'Send')}
              />
            </div>
          )}
        </section>

        {/* Right Dock: Live Browser Sandbox & Telemetry Log */}
        <aside className="browser-dock" style={{
          display: 'flex',
          flexDirection: 'column',
          backgroundColor: '#f8fafc',
          borderLeft: '1px solid #e2e8f0',
          padding: '0.85rem',
          gap: '0.65rem',
          height: '100%',
          overflowY: 'auto',
          boxSizing: 'border-box'
        }}>

          {/* Browser Preview Frame */}
          <BrowserPreview currentUrl={currentUrl} screenshotUrl={screenshotUrl} onInteract={handleBrowserInteract} />

        </aside>
      </main>
    </div>
  );
}
