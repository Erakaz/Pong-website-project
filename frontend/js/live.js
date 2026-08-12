

import { getState, subscribe } from './store.js';

const RETRY_BASE = 1000;
const RETRY_MAX = 15000;
const HEARTBEAT = 25000;
const CLOSE_NORMAL = 1000;

const listeners = new Map();
const onlineUsers = new Set();

let socket = null;
let retryTimer = null;
let heartbeatTimer = null;
let attempts = 0;
let wanted = false;

function url() {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${scheme}://${window.location.host}/ws/live`;
}

function emit(type, payload) {
  const set = listeners.get(type);
  if (!set) return;
  for (const listener of set) {
    try {
      listener(payload);
    } catch (error) {
      console.error(`Abonne « ${type} » en echec`, error);
    }
  }
}


export function on(type, listener) {
  if (!listeners.has(type)) listeners.set(type, new Set());
  listeners.get(type).add(listener);
  return () => listeners.get(type).delete(listener);
}

export function isOnline(userId) {
  return onlineUsers.has(userId);
}


export function seed(userIds) {
  for (const id of userIds) onlineUsers.add(id);
}

export function onlineSnapshot() {
  return new Set(onlineUsers);
}

function open() {
  if (!wanted || socket) return;

  let next;
  try {
    next = new WebSocket(url());
  } catch {
    return scheduleRetry();
  }
  socket = next;

  next.addEventListener('open', () => {
    attempts = 0;
    next.send(JSON.stringify({ type: 'auth', token: getState().accessToken }));
    heartbeatTimer = window.setInterval(() => {
      if (next.readyState === WebSocket.OPEN) next.send(JSON.stringify({ type: 'ping' }));
    }, HEARTBEAT);
    emit('status', { connected: true });
  });

  next.addEventListener('message', (event) => {
    let payload;
    try {
      payload = JSON.parse(event.data);
    } catch {
      return;
    }

    if (payload.type === 'ready') {
      onlineUsers.clear();
      for (const id of payload.online_friends || []) onlineUsers.add(id);
      emit('presence', null);
      return;
    }
    if (payload.type === 'presence') {
      if (payload.online) onlineUsers.add(payload.user_id);
      else onlineUsers.delete(payload.user_id);
    }
    emit(payload.type, payload);
  });

  next.addEventListener('close', (event) => {
    window.clearInterval(heartbeatTimer);
    heartbeatTimer = null;
    socket = null;
    onlineUsers.clear();
    emit('status', { connected: false });
    if (wanted && event.code !== CLOSE_NORMAL) scheduleRetry();
  });

  next.addEventListener('error', () => {});
}

function scheduleRetry() {
  if (!wanted || retryTimer !== null) return;
  const delay = Math.min(RETRY_BASE * 2 ** attempts, RETRY_MAX);
  attempts += 1;
  retryTimer = window.setTimeout(() => {
    retryTimer = null;
    open();
  }, delay);
}

function close() {
  wanted = false;
  if (retryTimer !== null) {
    window.clearTimeout(retryTimer);
    retryTimer = null;
  }
  if (heartbeatTimer !== null) {
    window.clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
  if (socket && socket.readyState <= WebSocket.OPEN) socket.close(CLOSE_NORMAL, 'deconnexion');
  socket = null;
  onlineUsers.clear();
}


export function bindToSession() {
  subscribe((state) => {
    const authenticated = Boolean(state.user && state.accessToken);
    if (authenticated && !wanted) {
      wanted = true;
      attempts = 0;
      open();
    } else if (!authenticated && wanted) {
      close();
    }
  });
}
