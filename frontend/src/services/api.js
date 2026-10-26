/**
 * API and WebSocket client for Nexagent Backend.
 */

const API_BASE = '/api';

async function authRequest(path, body) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail || 'Authentication request failed.');
  }
  return response.json();
}

export const signup = (email, password, name = '') => authRequest('/auth/signup', { email, password, name });
export const login = (email, password) => authRequest('/auth/login', { email, password });
export const logout = () => authRequest('/auth/logout', {});
export const startGuestSession = () => authRequest('/auth/guest', {});

export async function fetchCurrentUser(timeoutMs = 5000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_BASE}/auth/me`, {
      credentials: 'include',
      signal: controller.signal
    });
    if (response.status === 401) return null;
    if (!response.ok) return null;
    return await response.json();
  } catch (err) {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

export async function createTask(goal, file = null, parentTaskId = null, conversationId = null) {
  if (file && typeof file === 'object' && file.name) {
    const formData = new FormData();
    formData.append('goal', goal);
    formData.append('file', file);
    if (parentTaskId) formData.append('parent_task_id', parentTaskId);
    if (conversationId) formData.append('conversation_id', conversationId);
    const response = await fetch(`${API_BASE}/tasks/upload`, {
      method: 'POST',
      body: formData
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Failed to create task: ${response.statusText}`);
    }
    return response.json();
  }

  const payload = { goal };
  if (parentTaskId) payload.parent_task_id = parentTaskId;
  if (conversationId) payload.conversation_id = conversationId;

  const response = await fetch(`${API_BASE}/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to create task: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchTasks() {
  const response = await fetch(`${API_BASE}/tasks`);
  if (!response.ok) {
    throw new Error('Failed to fetch tasks.');
  }
  return response.json();
}

export async function clearAllTasks() {
  const response = await fetch(`${API_BASE}/tasks`, {
    method: 'DELETE'
  });
  if (!response.ok) {
    throw new Error('Failed to clear task history from database.');
  }
  return response.json();
}

export async function deleteTask(taskId) {
  const response = await fetch(`${API_BASE}/tasks/${taskId}`, {
    method: 'DELETE'
  });
  if (!response.ok) {
    throw new Error('Failed to delete task.');
  }
  return response.json();
}

export async function fetchTaskDetails(taskId) {
  const response = await fetch(`${API_BASE}/tasks/${taskId}`);
  if (!response.ok) {
    throw new Error('Failed to fetch task details.');
  }
  return response.json();
}

export async function submitHumanResponse(taskId, approved, responseData = {}) {
  const response = await fetch(`${API_BASE}/tasks/${taskId}/resume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved, response_data: responseData })
  });
  if (!response.ok) {
    throw new Error('Failed to submit response.');
  }
  return response.json();
}

export async function uploadInterventionFile(taskId, file) {
  const formData = new FormData();
  const files = Array.isArray(file) ? file : [file];
  files.forEach((item) => formData.append('files', item, item.webkitRelativePath || item.name));
  const response = await fetch(`${API_BASE}/tasks/${taskId}/intervention/upload`, {
    method: 'POST',
    body: formData
  });
  if (!response.ok) {
    throw new Error('Failed to upload intervention file.');
  }
  return response.json();
}

export async function cancelTask(taskId) {
  const response = await fetch(`${API_BASE}/tasks/${taskId}/cancel`, {
    method: 'POST'
  });
  if (!response.ok) {
    throw new Error('Failed to cancel task.');
  }
  return response.json();
}

export async function pauseTask(taskId) {
  const response = await fetch(`${API_BASE}/tasks/${taskId}/pause`, {
    method: 'POST'
  });
  if (!response.ok) {
    throw new Error('Failed to pause task.');
  }
  return response.json();
}

export async function resumeTask(taskId) {
  const response = await fetch(`${API_BASE}/tasks/${taskId}/unpause`, {
    method: 'POST'
  });
  if (!response.ok) {
    throw new Error('Failed to resume task.');
  }
  return response.json();
}

export async function sendBrowserInteraction(taskId, payload) {
  const response = await fetch(`${API_BASE}/tasks/${taskId}/interact`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error('Failed to send browser interaction.');
  }
  return response.json();
}

export function connectTaskWebSocket(taskId, onMessage) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  const wsUrl = `${protocol}//${host}/ws/tasks/${taskId}`;

  const ws = new WebSocket(wsUrl);

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch (e) {
      console.error('WS Parse Error:', e);
    }
  };

  ws.onerror = (err) => console.error('WS Error:', err);
  ws.onclose = () => console.log('WS Connection Closed.');

  return ws;
}
