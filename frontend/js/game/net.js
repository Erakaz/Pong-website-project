

import { getState } from '../store.js';

const RETRY_BASE = 500;
const RETRY_MAX = 8000;
const CLOSE_NORMAL = 1000;

export class MatchSocket {

  constructor(matchId, handlers = {}) {
    this.matchId = matchId;
    this.handlers = handlers;
    this.socket = null;
    this.closed = false;
    this.attempts = 0;
    this.retryTimer = null;
  }

  get url() {
    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    return `${scheme}://${window.location.host}/ws/game/${this.matchId}`;
  }

  connect() {
    if (this.closed) return;
    this.notifyStatus(this.attempts === 0 ? 'connecting' : 'reconnecting');

    let socket;
    try {
      socket = new WebSocket(this.url);
    } catch (error) {
      return this.scheduleRetry();
    }
    this.socket = socket;

    socket.addEventListener('open', () => {
      this.attempts = 0;
      this.notifyStatus('online');


      this.send({ type: 'join', token: getState().accessToken });
    });

    socket.addEventListener('message', (event) => {
      let payload;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      this.dispatch(payload);
    });

    socket.addEventListener('close', (event) => {
      this.socket = null;
      if (this.closed || event.code === CLOSE_NORMAL) {
        this.notifyStatus('closed');
        return;
      }
      this.notifyStatus('offline');
      this.scheduleRetry();
    });


    socket.addEventListener('error', () => {});
  }

  dispatch(payload) {
    const map = {
      joined: 'onJoined',
      state: 'onState',
      player: 'onPlayer',
      events: 'onEvents',
      opponent: 'onOpponent',
      end: 'onEnd',
      aborted: 'onAborted',
      error: 'onError',
      pong: null,
    };
    const name = map[payload.type];
    if (name && typeof this.handlers[name] === 'function') {
      this.handlers[name](payload);
    }
  }

  scheduleRetry() {
    if (this.closed || this.retryTimer !== null) return;
    const delay = Math.min(RETRY_BASE * 2 ** this.attempts, RETRY_MAX);
    this.attempts += 1;
    this.retryTimer = window.setTimeout(() => {
      this.retryTimer = null;
      this.connect();
    }, delay);
  }

  send(message) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(message));
      return true;
    }
    return false;
  }

  sendInput(side, direction) {
    this.send({ type: 'input', side, dir: direction });
  }

  notifyStatus(status) {
    if (typeof this.handlers.onStatus === 'function') this.handlers.onStatus(status);
  }

  close() {
    this.closed = true;
    if (this.retryTimer !== null) {
      window.clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
    if (this.socket && this.socket.readyState <= WebSocket.OPEN) {
      this.socket.close(CLOSE_NORMAL, 'navigation');
    }
    this.socket = null;
  }
}
