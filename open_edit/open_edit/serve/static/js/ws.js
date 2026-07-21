/* ============================================================
   ws.js — WebSocket client + event dispatch. The chat log
   functions (in chat.js) are called when events land; the
   app-level hook (loadProjectState on ``done``) is registered
   via ``setOnTurnDone`` so we don't have to import app.js
   from here (avoiding a circular dependency).

   The state machine for the WS connection state lives here:
   'disconnected' -> 'connecting' -> 'connected' (and back).
   Reconnect is exponential backoff capped at 10s.
   ============================================================ */

import { $ } from './dom.js';
import { state } from './state.js';
import {
  appendTextDelta,
  appendToolCard,
  completeToolCard,
  appendErrorMessage,
  appendRenderEvent,
  markTurnDone,
} from './chat.js';

export function setWsState(s) {
  state.wsState = s;
  const dot = $('#conn-status');
  if (!dot) return;
  dot.className = 'conn-status ' + s;
  dot.title = s.charAt(0).toUpperCase() + s.slice(1);
}

// Registered by app.js so we can call back into the project-state
// loader (and the renders refresh) on turn done without a circular
// import. Default: no-op.
let _onTurnDone = () => {};
export function setOnTurnDone(callback) {
  _onTurnDone = (typeof callback === 'function') ? callback : () => {};
}

export function connectWS() {
  if (!state.currentProjectId) return;
  // Close any existing socket.
  if (state.ws) {
    try { state.ws.close(); } catch {}
    state.ws = null;
  }
  // Clear any pending reconnect.
  if (state.reconnectTimer) {
    clearTimeout(state.reconnectTimer);
    state.reconnectTimer = null;
  }

  setWsState('connecting');
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${proto}//${location.host}/api/chat/${encodeURIComponent(state.currentProjectId)}`;
  let ws;
  try {
    ws = new WebSocket(url);
  } catch (e) {
    setWsState('disconnected');
    scheduleReconnect();
    return;
  }
  state.ws = ws;

  ws.onopen = () => {
    setWsState('connected');
    state.reconnectAttempts = 0;
  };

  ws.onmessage = (ev) => {
    let data;
    try { data = JSON.parse(ev.data); }
    catch { return; }
    handleWsEvent(data);
  };

  ws.onerror = () => {
    // onclose will fire next; we'll reconnect there.
  };

  ws.onclose = () => {
    setWsState('disconnected');
    state.ws = null;
    if (state.currentProjectId) scheduleReconnect();
  };
}

export function scheduleReconnect() {
  if (state.reconnectTimer) return;
  state.reconnectAttempts += 1;
  // Exponential backoff capped at 10s.
  const delay = Math.min(1000 * Math.pow(1.5, state.reconnectAttempts - 1), 10000);
  state.reconnectTimer = setTimeout(() => {
    state.reconnectTimer = null;
    connectWS();
  }, delay);
}

export function handleWsEvent(ev) {
  if (state.chatStatus) state.chatStatus.onEvent(ev);
  // v1.4 P1-3: route cost_update events to the cost badge.
  // The badge is focused (it only reacts to its own event
  // type), so this is a separate dispatch from the chat-status
  // indicator above.
  if (state.costBadge) state.costBadge.onEvent(ev);
  // v1.5: route verification_started / verification_result events
  // to the verification chip. Mirrors the chat-status / cost-badge
  // wiring pattern.
  if (state.verifyChip) state.verifyChip.onEvent(ev);
  switch (ev.type) {
    case 'ready':
      // Server ack; nothing to render.
      break;
    case 'text':
      appendTextDelta(ev.text || '');
      break;
    case 'tool_start':
      appendToolCard(ev.id || ((typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : `t-${Date.now()}`), ev.name, ev.input || {});
      break;
    case 'tool_result':
      completeToolCard(ev.id || '', ev.result, false);
      break;
    case 'error':
      // Could be a tool-level error (has tool_use_id) or a turn-level error.
      if (ev.tool_use_id && state.pendingToolCards.has(ev.tool_use_id)) {
        completeToolCard(ev.tool_use_id, { error: ev.message }, true);
      } else {
        appendErrorMessage(ev.message || 'Unknown error');
      }
      break;
    case 'render':
      appendRenderEvent(ev.path || '', ev.mode || 'proxy');
      break;
    case 'done':
      markTurnDone();
      // Auto-refresh project state so new ops / assets / notes show up.
      _onTurnDone();
      break;
    case 'cost_update':
      // The cost badge's onEvent was already invoked above the
      // switch (see the "v1.4 P1-3: route cost_update events"
      // comment); the chat-log switch only handles events that
      // mutate the log itself, so cost_update is a no-op here.
      break;
    default:
      // Unknown event type — ignore silently.
      break;
  }
}
