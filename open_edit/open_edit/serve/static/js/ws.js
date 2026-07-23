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

import { $, showToast } from './dom.js';
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

// Track whether the current socket was closed on purpose (project
// switch, settings save) so onclose doesn't scream "dropped" or start
// a reconnect storm against the new socket.
let _intentionalClose = false;
const MAX_RECONNECT_ATTEMPTS = 8;

export function connectWS() {
  // Always tear down the previous socket FIRST — even when the new
  // project id is empty ("— select —"), otherwise the old socket leaks
  // and keeps streaming the previous project's events.
  if (state.ws) {
    _intentionalClose = true;
    try { state.ws.close(); } catch {}
    state.ws = null;
  }
  // Clear any pending reconnect.
  if (state.reconnectTimer) {
    clearTimeout(state.reconnectTimer);
    state.reconnectTimer = null;
  }
  if (!state.currentProjectId) {
    setWsState('disconnected');
    return;
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
    // Stale socket: a newer connectWS() already replaced us.
    if (state.ws !== ws) { try { ws.close(); } catch {} return; }
    const wasReconnecting = state.reconnectAttempts > 0;
    setWsState('connected');
    state.reconnectAttempts = 0;
    if (wasReconnecting) {
      showToast('WebSocket reconnected', 'success');
    }
  };

  ws.onmessage = (ev) => {
    // Stale socket: drop its events so an old project's stream can't
    // bleed into the new project's chat log.
    if (state.ws !== ws) return;
    let data;
    try { data = JSON.parse(ev.data); }
    catch { return; }
    handleWsEvent(data);
  };

  ws.onerror = () => {
    // onclose will fire next; we'll reconnect there.
  };

  ws.onclose = (ev) => {
    const intentional = _intentionalClose;
    _intentionalClose = false;
    // Stale socket: a newer socket is already in place — do NOT null it
    // out, flip state, or schedule a reconnect (that used to kill the
    // fresh socket and duplicate the event stream).
    if (state.ws !== ws) return;
    setWsState('disconnected');
    state.ws = null;
    if (intentional) return;  // closed by us on purpose — stay quiet
    // 4404 = project not found (server-side close code): reconnecting
    // would loop forever against a dead project.
    if (ev && ev.code === 4404) {
      showToast('Project not found on server', 'error');
      return;
    }
    showToast('WebSocket connection dropped', 'error');
    if (state.currentProjectId) scheduleReconnect();
  };
}

export function scheduleReconnect() {
  if (state.reconnectTimer) return;
  if (state.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
    setWsState('disconnected');
    showToast('Connection lost — giving up. Reload to retry.', 'error');
    return;
  }
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
      completeToolCard(ev.id || '', ev.result, !!ev.is_error);
      break;
    case 'error':
      appendErrorMessage(ev.message || 'Unknown error');
      break;
    case 'render':
      appendRenderEvent(ev.path || '', ev.mode || 'proxy');
      break;
    case 'done':
      markTurnDone();
      // Auto-refresh project state so new ops / assets / notes show up.
      _onTurnDone();
      break;
    case 'cancelled':
      // Server ack of a cancel/stop request. The turn's ``done`` event
      // follows; we just settle the UI state here so the Stop button
      // doesn't look dead.
      markTurnDone();
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
