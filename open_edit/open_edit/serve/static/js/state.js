/* ============================================================
   state.js — shared application state, localStorage hydration,
   and the state-shape normalizers the API responses get piped
   through before they hit the UI (Prompt-1 backend vs Prompt-2
   contract). This module has no DOM dependency so it can be
   loaded by anything (including the Node-sandbox tests).
   ============================================================ */

export const state = {
  projects: [],
  currentProjectId: null,
  currentProjectState: null,
  conversationId: null,
  ws: null,
  wsState: 'disconnected', // 'disconnected' | 'connecting' | 'connected'
  reconnectAttempts: 0,
  reconnectTimer: null,
  editGraphRefreshTimer: null,
  // Tracks the in-flight assistant message + its tool cards by conv turn
  pendingAssistantMsg: null,
  pendingToolCards: new Map(), // tool_use_id -> DOM element
  // v1.4 P1-2: chat-status indicator state machine. Set in ``boot()``
  // once the DOM is ready. Driven by the WS event stream.
  chatStatus: null,
  // v1.5: verification chip state machine. Set in boot() once the DOM
  // is ready. Mirrors the chat-status wiring pattern.
  verifyChip: null,
  // v1.4 P1-3: cost badge state machine. Lives next to the
  // chat-status pill in the DOM; the agent loop's
  // ``cost_update`` WS event drives the label.
  costBadge: null,
};

// Hydrate from localStorage if it's available (browser). Tests stub
// it on globalThis; in pure-Node environments without the stub
// we leave the fields null.
try {
  if (typeof localStorage !== 'undefined') {
    state.currentProjectId = localStorage.getItem('open_edit.current_project_id') || null;
    state.conversationId = localStorage.getItem('open_edit.conversation_id') || null;
  }
} catch (e) {
  // localStorage can throw in private-mode browsers. Treat as missing.
}

// ----------------------------------------------------------
// State-shape normalisation
// (Prompt-1 backend vs Prompt-2 contract)
// ----------------------------------------------------------
export function normalizeAssets(rawAssets) {
  if (!Array.isArray(rawAssets)) return [];
  return rawAssets.map(a => ({
    hash: a.hash || a.id || '',
    filename: a.filename || a.name || 'unnamed',
    duration_s: a.duration_s ?? a.duration_sec ?? a.duration ?? 0,
    fps: a.fps || 0,
    width: a.width || 0,
    height: a.height || 0,
    codec: a.codec || '',
    has_audio: a.has_audio ?? false,
    // Servable URL the preview can set as ``<video src>``. v1.4 P0-2:
    // the backend's ``AssetInfo`` and the upload response both carry
    // this field (see ``GET /api/projects/{id}/assets/{hash}/file``).
    // Legacy shapes (no url) get an empty string so the preview
    // shows a clear "no preview available" state instead of crashing.
    url: a.url || a.stream_url || '',
    extra: a,
  }));
}

export function normalizeEdits(rawState) {
  // Prompt-2 contract uses state.edit_graph[]
  // Prompt-1 backend uses state.ops[] with {id, type, payload, effects}
  // v1.8 Wave 2: preserve full op data for edit-graph interactivity
  if (Array.isArray(rawState.edit_graph)) {
    return rawState.edit_graph.map(e => ({
      edit_id: e.edit_id || e.id || '',
      kind: e.kind || e.type || '',
      status: e.status || '',
      summary: e.summary || summarizeOpPayload(e.payload || {}),
      payload: e.payload || {},
      parent_id: e.parent_id || null,
      author: e.author || '',
      timestamp: e.timestamp || '',
    }));
  }
  if (Array.isArray(rawState.ops)) {
    return rawState.ops.map(o => ({
      edit_id: o.id || '',
      kind: o.type || '',
      status: o.status || 'committed',
      summary: summarizeOpPayload(o.payload || {}),
      payload: o.payload || {},
      parent_id: o.parent_id || null,
      author: o.author || '',
      timestamp: o.timestamp || '',
    }));
  }
  return [];
}

export function summarizeOpPayload(p) {
  if (!p || typeof p !== 'object') return '';
  const keys = ['label', 'filename', 'asset_hash', 'type', 'mode'];
  for (const k of keys) if (p[k]) return `${k}=${String(p[k]).slice(0, 60)}`;
  return JSON.stringify(p).slice(0, 80);
}

export function normalizeTimeline(raw) {
  if (!raw) return { num_tracks: 0, duration_sec: 0, clip_count: 0 };
  return {
    num_tracks: raw.num_tracks ?? 0,
    duration_sec: raw.duration_sec ?? raw.total_duration_s ?? raw.duration_s ?? 0,
    clip_count: raw.clip_count ?? raw.num_clips ?? 0,
    tracks: raw.tracks || [],
    overlays: raw.overlays || [],
  };
}

export function normalizeRenders(rawState) {
  // Prompt-2: state.last_renders[]
  // Prompt-1: separate /renders endpoint (handled in renderRendersList)
  if (Array.isArray(rawState.last_renders)) {
    return rawState.last_renders.map(r => ({
      path: r.path || '',
      mode: r.mode || 'proxy',
      timestamp: r.timestamp || r.created_at || '',
      size_bytes: r.size_bytes || 0,
    }));
  }
  return null;
}

export function normalizeNotes(rawState) {
  // Prompt-1: state.notes[] + pending_notes_count
  if (Array.isArray(rawState.notes)) {
    return {
      pending: rawState.pending_notes_count ?? rawState.pending_notes ?? 0,
      list: rawState.notes.map(n => ({
        id: n.id || '',
        timestamp: n.timestamp || 0,
        source: n.source || 'agent',
        text: n.text || '',
        status: n.status || 'pending',
      })),
    };
  }
  return { pending: rawState.pending_notes_count ?? 0, list: [] };
}
