/* ============================================================
   Open Edit — frontend SPA
   Vanilla JS, no external libraries.
   - REST client (fetch) for project CRUD + ingest + render
   - WebSocket client with auto-reconnect for chat
   - Defensive state parsing: accepts BOTH the Prompt-1 backend
     shape (snake_case: assets[].duration_s, ops[], timeline.num_clips)
     AND the Prompt-2 contract (camelCase: assets[].duration_sec,
     edit_graph[], timeline.num_tracks). Adjust as needed.
   ============================================================ */

(() => {
'use strict';

// ----------------------------------------------------------
// State
// ----------------------------------------------------------
const state = {
  projects: [],
  currentProjectId: localStorage.getItem('open_edit.current_project_id') || null,
  currentProjectState: null,
  conversationId: localStorage.getItem('open_edit.conversation_id') || null,
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
  // v1.4 P1-3: cost badge state machine. Lives next to the
  // chat-status pill in the DOM; the agent loop's
  // ``cost_update`` WS event drives the label.
  costBadge: null,
};

// ----------------------------------------------------------
// DOM helpers
// ----------------------------------------------------------
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'class') node.className = v;
    else if (k === 'dataset') Object.assign(node.dataset, v);
    else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'html') node.innerHTML = v;
    else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c == null) continue;
    node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  }
  return node;
}

function showToast(message, kind = '') {
  const t = $('#toast');
  t.textContent = message;
  t.className = 'toast ' + kind;
  setTimeout(() => t.classList.add('hidden'), 3000);
}

function fmtBytes(n) {
  if (!n && n !== 0) return '—';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
}

function fmtDuration(s) {
  if (!s || s <= 0) return '0:00';
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, '0')}`;
}

function fmtTime(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch { return iso; }
}

// ----------------------------------------------------------
// REST client
// ----------------------------------------------------------

// Extract the v1.4 ``{"error": "..."}`` (or legacy ``{"detail": "..."}``)
// from a failed response and surface it in the thrown Error so the rest of
// the UI (toasts / chat log) can show the actual reason rather than just
// the HTTP status. Falls back to the raw text body if the body isn't JSON.
async function _extractError(r, opName) {
  let msg = '';
  try {
    const body = await r.json();
    if (body && typeof body.error === 'string') msg = body.error;
    else if (body && typeof body.detail === 'string') msg = body.detail;
    else msg = JSON.stringify(body);
  } catch {
    try { msg = await r.text(); } catch { msg = ''; }
  }
  return new Error(msg ? `${opName}: ${msg}` : `${opName}: HTTP ${r.status}`);
}

const api = {
  async listProjects() {
    const r = await fetch('/api/projects');
    if (!r.ok) throw await _extractError(r, 'listProjects');
    return r.json();
  },

  async createProject(name) {
    const r = await fetch('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    if (!r.ok) throw await _extractError(r, 'createProject');
    return r.json();
  },

  async getProjectState(id) {
    const r = await fetch(`/api/projects/${encodeURIComponent(id)}`);
    if (!r.ok) throw await _extractError(r, 'getProjectState');
    return r.json();
  },

  async ingestFiles(id, files, onProgress) {
    const fd = new FormData();
    // Spec says field name is "files"; backend Prompt-1 uses "file".
    // Send under BOTH names for compatibility.
    for (const f of files) {
      fd.append('files', f, f.name);
      fd.append('file', f, f.name);
    }
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `/api/projects/${encodeURIComponent(id)}/ingest`);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) {
          onProgress(e.loaded / e.total);
        }
      };
      xhr.onload = async () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try { resolve(JSON.parse(xhr.responseText)); }
          catch { resolve({}); }
        } else {
          // Mirror the fetch path: parse the v1.4 ``{"error": "..."}`` body.
          const fakeResp = new Response(xhr.responseText, { status: xhr.status });
          reject(await _extractError(fakeResp, 'ingest'));
        }
      };
      xhr.onerror = () => reject(new Error('ingest: network error'));
      xhr.send(fd);
    });
  },

  async renderProject(id, mode) {
    const r = await fetch(`/api/projects/${encodeURIComponent(id)}/render`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode }),
    });
    if (!r.ok) throw await _extractError(r, 'render');
    return r.json();
  },

  async listRenders(id) {
    const r = await fetch(`/api/projects/${encodeURIComponent(id)}/renders`);
    if (!r.ok) {
      // ``listRenders`` is best-effort: the right panel shows whatever
      // the server has. We don't want a stale render failure to toast
      // repeatedly on every refresh, so swallow with an empty list.
      try {
        const fakeResp = new Response(await r.text(), { status: r.status });
        console.warn('listRenders failed:', (await _extractError(fakeResp, 'listRenders')).message);
      } catch { /* ignore */ }
      return [];
    }
    return r.json();
  },

  thumbnailUrl(id, path) {
    const q = path ? `?path=${encodeURIComponent(path)}` : '';
    return `/api/projects/${encodeURIComponent(id)}/thumbnail${q}`;
  },
};

// ----------------------------------------------------------
// State-shape normalisation
// (Prompt-1 backend vs Prompt-2 contract)
// ----------------------------------------------------------
function normalizeAssets(rawAssets) {
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

function normalizeEdits(rawState) {
  // Prompt-2 contract uses state.edit_graph[]
  // Prompt-1 backend uses state.ops[] with {id, type, payload, effects}
  if (Array.isArray(rawState.edit_graph)) {
    return rawState.edit_graph.map(e => ({
      edit_id: e.edit_id || e.id || '',
      kind: e.kind || e.type || '',
      status: e.status || '',
      summary: e.summary || JSON.stringify(e.payload || e).slice(0, 80),
    }));
  }
  if (Array.isArray(rawState.ops)) {
    return rawState.ops.map(o => ({
      edit_id: o.id || '',
      kind: o.type || '',
      status: o.status || 'committed',
      summary: summarizeOpPayload(o.payload || {}),
    }));
  }
  return [];
}

function summarizeOpPayload(p) {
  if (!p || typeof p !== 'object') return '';
  const keys = ['label', 'filename', 'asset_hash', 'type', 'mode'];
  for (const k of keys) if (p[k]) return `${k}=${String(p[k]).slice(0, 60)}`;
  return JSON.stringify(p).slice(0, 80);
}

function normalizeTimeline(raw) {
  if (!raw) return { num_tracks: 0, duration_sec: 0, clip_count: 0 };
  return {
    num_tracks: raw.num_tracks ?? 0,
    duration_sec: raw.duration_sec ?? raw.total_duration_s ?? raw.duration_s ?? 0,
    clip_count: raw.clip_count ?? raw.num_clips ?? 0,
  };
}

function normalizeRenders(rawState) {
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

function normalizeNotes(rawState) {
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

// ----------------------------------------------------------
// Project selector
// ----------------------------------------------------------
async function refreshProjects() {
  try {
    state.projects = await api.listProjects();
    renderProjectSelect();

    // If the saved project no longer exists, clear it.
    if (state.currentProjectId && !state.projects.some(p => p.id === state.currentProjectId)) {
      state.currentProjectId = null;
      localStorage.removeItem('open_edit.current_project_id');
    }
    // Auto-select if exactly one project exists and none is selected.
    if (!state.currentProjectId && state.projects.length === 1) {
      selectProject(state.projects[0].id);
    }
    // If no project is selected (and the list is empty), refresh the
    // chat log so the "no projects" hint replaces the generic placeholder.
    if (!state.currentProjectId) {
      clearChatLog();
    }
  } catch (e) {
    showToast(`Failed to load projects: ${e.message}`, 'error');
  }
}

function renderProjectSelect() {
  const sel = $('#project-select');
  sel.innerHTML = '';
  if (state.projects.length === 0) {
    sel.appendChild(el('option', { value: '' }, '— none —'));
    return;
  }
  sel.appendChild(el('option', { value: '' }, '— select —'));
  for (const p of state.projects) {
    const opt = el('option', { value: p.id }, `${p.name} (${p.num_assets || 0} assets)`);
    if (p.id === state.currentProjectId) opt.selected = true;
    sel.appendChild(opt);
  }
}

function selectProject(id) {
  if (id === state.currentProjectId) return;
  state.currentProjectId = id;
  if (id) localStorage.setItem('open_edit.current_project_id', id);
  else localStorage.removeItem('open_edit.current_project_id');

  // Reset conversation on project switch (each project has its own convs).
  state.conversationId = null;
  localStorage.removeItem('open_edit.conversation_id');
  clearChatLog();

  $('#project-select').value = id || '';
  loadProjectState();
  connectWS();
}

// ----------------------------------------------------------
// Project state (left + right panels)
// ----------------------------------------------------------
async function loadProjectState() {
  if (!state.currentProjectId) {
    state.currentProjectState = null;
    renderAssets([]);
    renderEditGraph([]);
    renderRendersList([]);
    renderNotesSummary({ pending: 0, list: [] });
    setChatEnabled(false);
    return;
  }
  setChatEnabled(true);
  try {
    const s = await api.getProjectState(state.currentProjectId);
    state.currentProjectState = s;
    renderAssets(normalizeAssets(s.assets));
    renderEditGraph(normalizeEdits(s));
    renderNotesSummary(normalizeNotes(s));
    const inlineRenders = normalizeRenders(s);
    if (inlineRenders) renderRendersList(inlineRenders);
    else refreshRendersList();
  } catch (e) {
    showToast(`Failed to load project: ${e.message}`, 'error');
  }
}

function renderAssets(assets) {
  const list = $('#assets-list');
  list.innerHTML = '';
  if (!assets.length) {
    list.appendChild(el('div', { class: 'empty-state' }, ['No assets yet.', el('br'), 'Upload one below.']));
    return;
  }
  for (const a of assets) {
    const icon = assetIcon(a);
    const card = el('div', { class: 'asset-card' }, [
      el('div', { class: 'asset-icon' }, [icon]),
      el('div', { class: 'asset-meta' }, [
        el('div', { class: 'asset-filename' }, [a.filename]),
        el('div', { class: 'asset-sub' }, [
          `${fmtDuration(a.duration_s)}`,
          a.width && a.height ? ` · ${a.width}×${a.height}` : '',
          a.codec ? ` · ${a.codec}` : '',
          a.has_audio ? ' · audio' : '',
        ].filter(Boolean).join('')),
      ]),
    ]);
    card.addEventListener('click', () => openAssetPreview(a));
    list.appendChild(card);
  }
}

function assetIcon(a) {
  const fn = (a.filename || '').toLowerCase();
  if (/\.(mp4|mov|avi|mkv|webm)$/.test(fn)) return '🎬';
  if (/\.(mp3|wav|aac|flac|m4a)$/.test(fn)) return '🎵';
  if (/\.(png|jpg|jpeg|gif|webp|bmp)$/.test(fn)) return '🖼️';
  return '📄';
}

function renderEditGraph(edits) {
  const list = $('#edit-graph-list');
  list.innerHTML = '';
  if (!edits.length) {
    list.appendChild(el('div', { class: 'empty-state' }, ['No edits yet.', el('br'), 'Ask the agent to do something.']));
    return;
  }
  // Show most recent first.
  for (const e of [...edits].reverse().slice(0, 50)) {
    list.appendChild(el('div', { class: 'edit-card' }, [
      el('div', {}, [
        el('span', { class: 'edit-kind' }, [e.kind]),
        e.status ? el('span', { class: 'edit-status' }, [e.status]) : null,
      ]),
      el('div', { class: 'edit-summary' }, [e.summary]),
    ]));
  }
}

function renderNotesSummary(notes) {
  const div = $('#notes-summary');
  if (!notes || !notes.pending) {
    div.textContent = 'No pending notes.';
  } else {
    div.textContent = `${notes.pending} pending note${notes.pending === 1 ? '' : 's'}`;
  }
}

function renderRendersList(renders) {
  const list = $('#renders-list');
  list.innerHTML = '';
  if (!renders.length) {
    list.appendChild(el('div', { class: 'empty-state' }, ['No renders yet.']));
    return;
  }
  // Newest first.
  for (const r of [...renders].reverse()) {
    const name = (r.path || '').split('/').pop() || 'render.mp4';
    const item = el('div', { class: 'render-item' }, [
      el('div', { class: 'render-thumb' }, ['🎞️']),
      el('div', { class: 'render-meta' }, [
        el('div', { class: 'render-name' }, [name]),
        el('div', { class: 'render-sub' }, [
          r.mode || 'proxy',
          ' · ',
          fmtBytes(r.size_bytes),
          r.timestamp ? ` · ${fmtTime(r.timestamp)}` : '',
        ]),
      ]),
    ]);
    item.addEventListener('click', () => {
      // Try to play it directly via the path; if the path isn't a URL,
      // we can't easily serve it without a route — open the path as a link.
      if (r.path && /^https?:/.test(r.path)) {
        window.open(r.path, '_blank');
      } else if (r.path) {
        // Fall back: copy the path to clipboard and toast.
        navigator.clipboard?.writeText(r.path).catch(() => {});
        showToast(`Render path: ${r.path}`);
      }
    });
    list.appendChild(item);
  }
}

async function refreshRendersList() {
  if (!state.currentProjectId) return;
  try {
    const renders = await api.listRenders(state.currentProjectId);
    renderRendersList(renders);
  } catch {
    // Silent fail — renders list is non-critical.
  }
}

// ----------------------------------------------------------
// Asset preview modal
// ----------------------------------------------------------
function openAssetPreview(asset) {
  const titleEl = $('#asset-preview-title');
  const video = $('#asset-preview-video');
  // v1.4 P0-2: the backend's ``AssetInfo.url`` is a servable route
  // (e.g. ``/api/projects/abc/assets/13957.../file``) that streams the
  // asset bytes with the right ``Content-Type`` and Range support.
  // Set it as the ``<video>`` src so the browser actually plays it.
  if (asset.url) {
    video.src = asset.url;
    titleEl.textContent = asset.filename;
  } else {
    // No URL — clear any previous source and annotate the title so
    // the user knows why the player is blank (instead of staring at
    // an empty modal wondering if it's broken). The bare filename
    // alone would be indistinguishable from a working preview that
    // hasn't loaded yet.
    video.removeAttribute('src');
    titleEl.textContent = `${asset.filename} (no preview available)`;
  }
  video.load();
  showModal('modal-asset-preview');
}

// ----------------------------------------------------------
// Notes modal
// ----------------------------------------------------------
function openNotesModal() {
  const notes = normalizeNotes(state.currentProjectState || {});
  const list = $('#notes-list');
  list.innerHTML = '';
  if (!notes.list.length) {
    list.appendChild(el('div', { class: 'empty-state' }, ['No notes yet.']));
  } else {
    for (const n of notes.list) {
      list.appendChild(el('div', { class: 'note-item' }, [
        el('div', { class: 'note-ts' }, [
          `[${fmtDuration(n.timestamp)}] · ${n.source} · ${n.status}`,
        ]),
        el('div', { class: 'note-text' }, [n.text]),
      ]));
    }
  }
  showModal('modal-notes');
}

// ----------------------------------------------------------
// Modal helpers
// ----------------------------------------------------------
function showModal(id) { $('#' + id).classList.remove('hidden'); }
function hideModal(id) { $('#' + id).classList.add('hidden'); }
function hideAllModals() { $$('.modal').forEach(m => m.classList.add('hidden')); }

// ----------------------------------------------------------
// Chat log
// ----------------------------------------------------------
function clearChatLog() {
  const log = $('#chat-log');
  log.innerHTML = '';
  // If there are no projects, the user can't chat — show a hint with
  // the recovery command (v1.4 P0-1: "no projects found" must not be
  // an opaque empty state). Otherwise the generic placeholder.
  if (state.projects && state.projects.length === 0) {
    log.appendChild(el('div', { class: 'empty-state' }, [
      'No projects yet. Run ',
      el('code', {}, ['open_edit init <root>/<name>']),
      ' in a terminal, then click ⟳ to refresh.',
    ]));
  } else {
    log.appendChild(el('div', { class: 'empty-state' }, ['Select a project to start chatting.']));
  }
  state.pendingAssistantMsg = null;
  state.pendingToolCards.clear();
}

function ensureChatPlaceholderGone() {
  const log = $('#chat-log');
  const ph = log.querySelector('.empty-state');
  if (ph) ph.remove();
}

function appendUserMessage(text) {
  ensureChatPlaceholderGone();
  const msg = el('div', { class: 'msg msg-user' }, [text]);
  $('#chat-log').appendChild(msg);
  scrollChatToBottom();
}

function startAssistantMessage() {
  ensureChatPlaceholderGone();
  const msg = el('div', { class: 'msg msg-bot' }, []);
  $('#chat-log').appendChild(msg);
  state.pendingAssistantMsg = msg;
  state.pendingToolCards.clear();
  return msg;
}

function appendTextDelta(text) {
  if (!state.pendingAssistantMsg) startAssistantMessage();
  const msg = state.pendingAssistantMsg;
  // Append a text node; we accumulate in the existing node.
  // If the last child is a text node, append to it; otherwise create one.
  const last = msg.lastChild;
  if (last && last.nodeType === Node.TEXT_NODE) {
    last.textContent += text;
  } else {
    msg.appendChild(document.createTextNode(text));
  }
  scrollChatToBottom();
}

function appendToolCard(toolUseId, name, input) {
  ensureChatPlaceholderGone();
  const inputStr = (() => {
    try { return JSON.stringify(input); } catch { return String(input); }
  })();

  const spinner = el('div', { class: 'spinner' });
  const body = el('div', { class: 'tool-body' }, [
    el('div', { class: 'tool-name' }, [name]),
    el('div', { class: 'tool-input' }, [inputStr]),
  ]);
  const result = el('div', { class: 'tool-result hidden' });

  // v1.4 P1-1: search_assets gets a dedicated placeholder region that
  // the result panel replaces. The text-based resultEl stays hidden
  // but kept in the DOM for compatibility with ``completeToolCard``.
  const searchPanel = name === 'search_assets'
    ? el('div', { class: 'search-results-placeholder' })
    : null;

  const card = el('div', { class: 'tool-card' }, [
    el('div', { class: 'gear' }, ['⚙']),
    body,
    searchPanel,
    spinner,
    result,
  ]);
  // Insert BEFORE the pending assistant text message if it exists,
  // so tool cards appear above the final text. If there's no pending
  // assistant message yet, just append.
  if (state.pendingAssistantMsg && state.pendingAssistantMsg.textContent.length === 0) {
    // Replace the empty pending message with the tool card.
    state.pendingAssistantMsg.replaceWith(card);
    state.pendingAssistantMsg = null;
  } else {
    $('#chat-log').appendChild(card);
  }
  state.pendingToolCards.set(
    toolUseId,
    { card, spinner, result, name, searchPanel },
  );
  scrollChatToBottom();
}

function completeToolCard(toolUseId, result, isError = false) {
  const entry = state.pendingToolCards.get(toolUseId);
  if (!entry) {
    // No matching start event; emit a compact completed card.
    const card = el('div', { class: 'tool-card' }, [
      el('div', { class: 'gear' }, ['⚙']),
      el('div', { class: 'tool-body' }, [
        el('div', { class: 'tool-name' }, ['(result)']),
        el('div', { class: 'tool-result' + (isError ? ' failed' : '') }, [truncate(JSON.stringify(result), 200)]),
      ]),
    ]);
    $('#chat-log').appendChild(card);
    scrollChatToBottom();
    return;
  }
  const { card, spinner, result: resultEl, name, searchPanel } = entry;
  spinner.remove();
  // v1.4 P1-1: delegate to the dedicated results panel renderer for
  // search_assets. The result shape matches what the Python tool
  // returns (see pyagent_search_assets.search_assets).
  if (name === 'search_assets' && searchPanel) {
    const panel = appendSearchResults(result || {}, searchPanel);
    if (panel) {
      // Replace the placeholder with the real panel.
      searchPanel.replaceWith(panel);
    }
    scrollChatToBottom();
    return;
  }
  const text = (() => {
    try {
      const r = typeof result === 'string' ? JSON.parse(result) : result;
      if (r && r.error) return `✗ ${r.error}`;
      return `✓ ${truncate(JSON.stringify(r), 160)}`;
    } catch {
      return `✓ ${truncate(String(result), 160)}`;
    }
  })();
  resultEl.textContent = text;
  resultEl.className = 'tool-result' + (isError ? ' failed' : '');
  resultEl.classList.remove('hidden');
  scrollChatToBottom();
}

// ----------------------------------------------------------
// Search results panel (v1.4 P1-1)
//
// Renders one card per result with a thumbnail, title, license badge,
// attribution hint, and an "Add to project" button. When the tool
// returns an error (e.g. the API key is missing), renders a clear
// error state so the user can fix the env and retry.
//
// The wire shape is the same dict the Python tool returns, so we
// never re-fetch or re-shape the data — we render what the LLM saw.
// ----------------------------------------------------------
function appendSearchResults(result, mountPoint) {
  const root = mountPoint
    ? mountPoint
    : (el('div', { class: 'search-results' }));
  if (!root.classList.contains('search-results')) {
    root.classList.add('search-results');
  }
  // Empty out any previous render (e.g. when re-rendering the same
  // panel after a follow-up search).
  while (root.firstChild) root.removeChild(root.firstChild);

  if (result && result.error) {
    // Error state: a clear message + the cause.
    const errBox = el('div', { class: 'search-results-error' }, [
      el('div', { class: 'search-results-error-head' }, ['⚠ Search failed']),
      el('div', { class: 'search-results-error-body' }, [result.error]),
    ]);
    root.appendChild(errBox);
    return root;
  }

  const results = (result && result.results) || [];
  if (results.length === 0) {
    root.appendChild(el('div', { class: 'search-results-empty' }, [
      'No results. Try a different query.',
    ]));
    return root;
  }

  // Header summarising the query (so the user sees what was searched).
  const query = result.query || '';
  const kind = result.kind || '';
  if (query || kind) {
    const headBits = [];
    if (query) headBits.push(`for "${query}"`);
    if (kind) headBits.push(`(${kind})`);
    root.appendChild(el('div', { class: 'search-results-head' }, [
      `${results.length} result${results.length === 1 ? '' : 's'} ${headBits.join(' ')}`,
    ]));
  }

  // Grid of result cards.
  const grid = el('div', { class: 'search-results-grid' });
  for (const r of results) {
    grid.appendChild(_renderSearchResultCard(r));
  }
  root.appendChild(grid);
  return root;
}

function _renderSearchResultCard(r) {
  // License badge color: red for attribution-required, yellow for
  // permissive-but-credit-appreciated, green for public-domain.
  const license = (r && r.license) || 'Unknown';
  const licenseClass = r && r.attribution_required
    ? 'license-badge attr-required'
    : (license.toLowerCase().includes('cc0') || license.toLowerCase().includes('pexels')
        ? 'license-badge permissive'
        : 'license-badge');

  // Thumbnail: an <img> that fails soft if the upstream CDN is down.
  const thumb = el('img', {
    class: 'result-thumb',
    src: r.thumbnail_url || '',
    alt: r.title || '',
    loading: 'lazy',
  });
  thumb.addEventListener('error', () => {
    thumb.classList.add('thumb-error');
    thumb.replaceWith(el('div', { class: 'result-thumb thumb-error' }, ['(no preview)']));
  });

  const titleText = r.title || r.id || '(untitled)';
  const metaBits = [];
  if (r.kind) metaBits.push(r.kind);
  if (r.duration_seconds != null) metaBits.push(fmtDuration(r.duration_seconds));

  const card = el('div', { class: 'result-card', 'data-result-id': r.id || '' }, [
    thumb,
    el('div', { class: 'result-body' }, [
      el('div', { class: 'result-title' }, [titleText]),
      metaBits.length ? el('div', { class: 'result-meta' }, [metaBits.join(' · ')]) : null,
      el('div', { class: licenseClass }, [license]),
      r.attribution
        ? el('div', { class: 'result-attribution' }, [r.attribution])
        : null,
      el('button', {
        class: 'btn btn-secondary btn-sm result-import-btn',
        type: 'button',
      }, ['+ Add to project']),
    ]),
  ]);
  // Wire the import button. The simplest reliable cross-LLM path is
  // to send a chat message asking the assistant to import this result;
  // the assistant's tool schema already knows the import_asset shape.
  const btn = card.querySelector('.result-import-btn');
  if (btn) {
    btn.addEventListener('click', () => {
      const id = r.id || '';
      const ok = sendChatMessage(
        `Please import the search result with id "${id}" into the project.`
      );
      if (ok) {
        btn.disabled = true;
        btn.textContent = 'Requested…';
      }
    });
  }
  return card;
}

function appendRenderEvent(path, mode) {
  const card = el('div', { class: 'render-card' }, [
    el('div', { class: 'render-icon' }, ['✓']),
    el('div', {}, [
      el('div', {}, [`Rendered (${mode})`]),
      el('div', { class: 'render-path' }, [path || '(no path)']),
    ]),
  ]);
  $('#chat-log').appendChild(card);
  scrollChatToBottom();
  // Refresh the renders list since a new one likely landed.
  refreshRendersList();
}

function appendErrorMessage(message) {
  const msg = el('div', { class: 'msg msg-error' }, [`⚠ ${message}`]);
  $('#chat-log').appendChild(msg);
  scrollChatToBottom();
}

function markTurnDone() {
  // If the assistant message has no text content (only tool cards were
  // emitted), remove the empty bubble.
  if (state.pendingAssistantMsg && state.pendingAssistantMsg.textContent.trim() === '') {
    state.pendingAssistantMsg.remove();
  }
  state.pendingAssistantMsg = null;
  state.pendingToolCards.clear();
}

function truncate(s, n) {
  if (!s) return '';
  return s.length <= n ? s : s.slice(0, n - 1) + '…';
}

function scrollChatToBottom() {
  const log = $('#chat-log');
  log.scrollTop = log.scrollHeight;
}

// ----------------------------------------------------------
// Chat status indicator (v1.4 P1-2)
// ----------------------------------------------------------
// A small state machine that surfaces "AI is running" / "Running
// <tool>…" feedback near the chat input. The state is driven by the
// same WS events the chat log already consumes (see ``handleWsEvent``).
// Exposed as ``createChatStatus`` so Node-sandbox tests can drive it
// without a real DOM (see ``tests/test_serve_chat_status.py``).
//
// States: ``idle`` | ``thinking`` | ``tool_running``. ``idle`` is the
// resting state (no in-flight turn). ``thinking`` is entered
// immediately on ``send()`` and on a ``text`` event. A ``tool_start``
// event transitions to ``tool_running`` (with the tool name carried in
// the label) and stays there until ``tool_result``, which goes back to
// ``thinking`` so the user sees the model is still alive. The
// ``error`` and ``done`` events are both terminal — per the brief,
// the indicator "clears within one frame of ``DONE`` or ``error``",
// and both events converge on ``idle``. The error message itself is
// surfaced through the chat log / toast (see ``handleWsEvent``) so the
// chat-status pill does not need to render an error state.
function createChatStatus(element) {
  let currentState = 'idle';
  let currentToolName = null;
  const labelEl = element && element.querySelector
    ? element.querySelector('.chat-status-text')
    : null;

  function setState(next, payload) {
    currentState = next;
    currentToolName = (payload && payload.name) || null;
    if (!element) return;
    // Use setAttribute rather than ``element.dataset.state`` so the
    // same code path is exercised by the Node-sandbox test stubs
    // (which intercept setAttribute but don't proxy property writes
    // to the ``dataset`` object).
    element.setAttribute('data-state', next);
    if (next === 'idle') {
      element.classList.add('hidden');
    } else {
      element.classList.remove('hidden');
    }
    if (labelEl) labelEl.textContent = statusLabel(next, currentToolName);
  }

  // Set the initial state explicitly so the DOM attribute, the
  // ``hidden`` class, and the label are all in sync — and so test
  // stubs that start in an ``unset`` state see the same first write
  // a real browser would.
  setState('idle');

  return {
    send() {
      // User just clicked Send — show the indicator immediately, even
      // before the first WS event arrives. This is the "no visual
      // indication of what the AI is doing" gap the brief calls out.
      setState('thinking');
    },
    onEvent(ev) {
      if (!ev || typeof ev.type !== 'string') return;
      switch (ev.type) {
        case 'text':
          // First text delta confirms the model is responding. If a
          // tool is running we leave it alone (the tool label is more
          // useful); otherwise switch to thinking.
          if (currentState !== 'tool_running') setState('thinking');
          break;
        case 'tool_start':
          setState('tool_running', { name: ev.name });
          break;
        case 'tool_result':
          // Tool finished — the model will either emit more text or
          // ``done`` next. Either way we're back to "thinking" until
          // the turn ends.
          if (currentState === 'tool_running') setState('thinking');
          break;
        case 'error':
          // Per the brief, the indicator clears within one frame of
          // ``DONE`` or ``error``. The error message itself is shown
          // via the chat log / toast (see ``handleWsEvent``), so the
          // chat-status pill does not render an error state.
          setState('idle');
          break;
        case 'done':
          setState('idle');
          break;
        // ``ready`` and ``render`` don't change chat-status state.
      }
    },
    reset() { setState('idle'); },
    getState() { return { state: currentState, toolName: currentToolName }; },
  };
}

function statusLabel(s, toolName) {
  if (s === 'thinking') return 'AI thinking…';
  if (s === 'tool_running') return `Running ${toolName || 'tool'}…`;
  return '';
}

// ----------------------------------------------------------
// Cost badge (v1.4 P1-3)
// ----------------------------------------------------------
// A small monospace pill that displays the per-turn + cumulative
// session cost, or an honest "cost n/a" state when the LLM
// provider doesn't report a per-token bill (e.g. the ``pi`` path
// through opencode-go, which is subscription-billed).
//
// Driven by the ``cost_update`` WS event from the agent loop:
//   {type, turn_tokens, turn_cost_usd, session_cost_usd, source}
//
// The badge is intentionally focused: it only reacts to
// ``cost_update``. Other WS events (text, tool_start, done,
// error) are handled by the chat-status indicator above it. This
// separation of concerns is what the brief meant by "the cost
// badge should not duplicate the chat-status indicator's logic".
//
// Exposed as ``window.OpenEdit.__testHooks.createCostBadge`` so
// Node-sandbox tests can drive the badge without a real DOM
// (see ``tests/test_serve_cost_badge.py``).
function createCostBadge(element) {
  const labelEl = element && element.querySelector
    ? element.querySelector('.cost-badge-text')
    : null;

  function setLabel(text) {
    if (labelEl) labelEl.textContent = text;
  }

  function setSource(source) {
    if (!element) return;
    // Use setAttribute (same pattern as createChatStatus) so the
    // Node-sandbox test stubs that intercept setAttribute still work.
    element.setAttribute('data-source', source);
  }

  function setVisible(visible) {
    if (!element) return;
    if (visible) element.classList.remove('hidden');
    else element.classList.add('hidden');
  }

  function formatUsd(n) {
    // 2-4 fraction digits depending on magnitude. Very small
    // numbers (typical for a single pi turn) get 4 digits so
    // they don't show as "$0.00" when the user actually did
    // spend something. Larger numbers get 2 digits for compactness.
    if (n === 0) return '$0.00';
    if (n < 0.01) return '$' + n.toFixed(4);
    return '$' + n.toFixed(2);
  }

  // Start hidden — the badge appears only when the first
  // ``cost_update`` arrives, so we never show a stale label.
  setVisible(false);
  setSource('unavailable');
  setLabel('');

  return {
    onEvent(ev) {
      if (!ev || ev.type !== 'cost_update') return;
      const source = (ev.source === 'pi' || ev.source === 'computed')
        ? ev.source : 'unavailable';
      setSource(source);
      setVisible(true);
      if (source === 'unavailable') {
        // The brief: "When source == unavailable, show something
        // honest like 'cost n/a (subscription)' instead of a
        // fake $0.00." The exact wording is a UX choice; this
        // is the suggested form. Tests pin that we say "n/a"
        // and don't show a $0.00 fake.
        setLabel('cost n/a (subscription)');
        return;
      }
      const turnCost = Number(ev.turn_cost_usd) || 0;
      const sessionCost = Number(ev.session_cost_usd) || 0;
      setLabel(`${formatUsd(turnCost)} this turn · ${formatUsd(sessionCost)} session`);
    },
    reset() {
      setVisible(false);
      setSource('unavailable');
      setLabel('');
    },
  };
}

// ----------------------------------------------------------
// WebSocket client
// ----------------------------------------------------------
function setWsState(s) {
  state.wsState = s;
  const dot = $('#conn-status');
  dot.className = 'conn-status ' + s;
  dot.title = s.charAt(0).toUpperCase() + s.slice(1);
}

function connectWS() {
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

function scheduleReconnect() {
  if (state.reconnectTimer) return;
  state.reconnectAttempts += 1;
  // Exponential backoff capped at 10s.
  const delay = Math.min(1000 * Math.pow(1.5, state.reconnectAttempts - 1), 10000);
  state.reconnectTimer = setTimeout(() => {
    state.reconnectTimer = null;
    connectWS();
  }, delay);
}

function handleWsEvent(ev) {
  if (state.chatStatus) state.chatStatus.onEvent(ev);
  // v1.4 P1-3: route cost_update events to the cost badge.
  // The badge is focused (it only reacts to its own event
  // type), so this is a separate dispatch from the chat-status
  // indicator above.
  if (state.costBadge) state.costBadge.onEvent(ev);
  switch (ev.type) {
    case 'ready':
      // Server ack; nothing to render.
      break;
    case 'text':
      appendTextDelta(ev.text || '');
      break;
    case 'tool_start':
      appendToolCard(ev.id || crypto.randomUUID(), ev.name, ev.input || {});
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
      loadProjectState();
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

function sendChatMessage(text) {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    showToast('Not connected. Retrying…', 'error');
    scheduleReconnect();
    return false;
  }
  // Generate a conversation id if we don't have one yet.
  if (!state.conversationId) {
    state.conversationId = crypto.randomUUID();
    localStorage.setItem('open_edit.conversation_id', state.conversationId);
  }
  // The Prompt-1 backend accepts {message, conv_id}. The Prompt-2 contract
  // uses {type: "user_message", message, conversation_id}. Send BOTH shapes.
  const payload = {
    type: 'user_message',
    message: text,
    conversation_id: state.conversationId,
    conv_id: state.conversationId,
  };
  try {
    state.ws.send(JSON.stringify(payload));
    return true;
  } catch (e) {
    showToast(`Send failed: ${e.message}`, 'error');
    return false;
  }
}

// ----------------------------------------------------------
// Chat input
// ----------------------------------------------------------
function setChatEnabled(enabled) {
  $('#chat-input').disabled = !enabled;
  $('#btn-send').disabled = !enabled;
  if (enabled) $('#chat-input').focus();
}

function handleSend() {
  const input = $('#chat-input');
  const text = input.value.trim();
  if (!text) return;
  if (!state.currentProjectId) {
    showToast('Select or create a project first.', 'error');
    return;
  }
  if (sendChatMessage(text)) {
    appendUserMessage(text);
    input.value = '';
    autoGrowInput();
    if (state.chatStatus) state.chatStatus.send();
  }
}

function autoGrowInput() {
  const ta = $('#chat-input');
  ta.style.height = 'auto';
  ta.style.height = Math.min(ta.scrollHeight, 140) + 'px';
}

// ----------------------------------------------------------
// Upload
// ----------------------------------------------------------
async function handleFiles(files) {
  if (!state.currentProjectId) {
    showToast('Select or create a project first.', 'error');
    return;
  }
  if (!files || !files.length) return;

  const prog = $('#upload-progress');
  prog.classList.remove('hidden');
  prog.innerHTML = '';
  prog.appendChild(el('div', {}, [`Uploading ${files.length} file${files.length === 1 ? '' : 's'}…`]));
  const bar = el('div', { class: 'bar' }, [el('div', { class: 'bar-fill', style: 'width:0%' })]);
  prog.appendChild(bar);

  try {
    await api.ingestFiles(state.currentProjectId, files, (p) => {
      bar.querySelector('.bar-fill').style.width = `${Math.round(p * 100)}%`;
    });
    prog.querySelector('div').textContent = `Ingested ${files.length} file${files.length === 1 ? '' : 's'}.`;
    showToast(`Ingested ${files.length} file${files.length === 1 ? '' : 's'}`, 'success');
    // Reload state to show new assets.
    await loadProjectState();
  } catch (e) {
    prog.querySelector('div').textContent = `Upload failed: ${e.message}`;
    showToast(`Upload failed: ${e.message}`, 'error');
  } finally {
    setTimeout(() => prog.classList.add('hidden'), 3000);
  }
}

// ----------------------------------------------------------
// Render buttons
// ----------------------------------------------------------
async function triggerRender(mode) {
  if (!state.currentProjectId) {
    showToast('Select or create a project first.', 'error');
    return;
  }
  showToast(`Rendering ${mode}…`);
  try {
    const job = await api.renderProject(state.currentProjectId, mode);
    // Poll job status (best-effort).
    pollRenderJob(job.job_id, mode);
  } catch (e) {
    showToast(`Render failed: ${e.message}`, 'error');
  }
}

async function pollRenderJob(jobId, mode) {
  if (!state.currentProjectId || !jobId) return;
  let attempts = 0;
  const maxAttempts = 120; // 10 min at 5s polling
  const poll = async () => {
    attempts += 1;
    if (attempts > maxAttempts) return;
    try {
      const r = await fetch(`/api/projects/${encodeURIComponent(state.currentProjectId)}/render_jobs/${encodeURIComponent(jobId)}`);
      if (!r.ok) return;
      const job = await r.json();
      if (job.status === 'complete') {
        showToast(`Render complete: ${job.output_path || '(output)'}`, 'success');
        refreshRendersList();
        return;
      }
      if (job.status === 'failed') {
        showToast(`Render failed: ${job.error || 'unknown'}`, 'error');
        return;
      }
      setTimeout(poll, 2000);
    } catch {
      // network blip — keep polling
      setTimeout(poll, 2000);
    }
  };
  setTimeout(poll, 1000);
}

// ----------------------------------------------------------
// Edit graph auto-refresh
// ----------------------------------------------------------
function startEditGraphRefresh() {
  stopEditGraphRefresh();
  state.editGraphRefreshTimer = setInterval(async () => {
    if (!state.currentProjectId) return;
    try {
      const s = await api.getProjectState(state.currentProjectId);
      state.currentProjectState = s;
      renderAssets(normalizeAssets(s.assets));
      renderEditGraph(normalizeEdits(s));
      renderNotesSummary(normalizeNotes(s));
    } catch {
      // silent
    }
  }, 5000);
}
function stopEditGraphRefresh() {
  if (state.editGraphRefreshTimer) {
    clearInterval(state.editGraphRefreshTimer);
    state.editGraphRefreshTimer = null;
  }
}

// ----------------------------------------------------------
// Wire up the DOM
// ----------------------------------------------------------
function bindEvents() {
  // Project selector
  $('#project-select').addEventListener('change', (e) => selectProject(e.target.value));
  $('#btn-new-project').addEventListener('click', () => {
    $('#new-project-name').value = '';
    showModal('modal-new-project');
    setTimeout(() => $('#new-project-name').focus(), 50);
  });
  $('#btn-refresh-project').addEventListener('click', refreshProjects);
  $('#btn-create-project').addEventListener('click', async () => {
    const name = $('#new-project-name').value.trim();
    if (!name) return;
    try {
      const info = await api.createProject(name);
      hideModal('modal-new-project');
      await refreshProjects();
      selectProject(info.id);
      showToast(`Created project "${info.name}"`, 'success');
    } catch (e) {
      showToast(`Create failed: ${e.message}`, 'error');
    }
  });
  $('#new-project-name').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') $('#btn-create-project').click();
  });

  // Tabs (left panel)
  $$('.panel-tabs .tab').forEach((t) => {
    t.addEventListener('click', () => {
      $$('.panel-tabs .tab').forEach(x => x.classList.remove('active'));
      $$('.tab-content').forEach(x => x.classList.remove('active'));
      t.classList.add('active');
      $(`.tab-content[data-tab="${t.dataset.tab}"]`).classList.add('active');
    });
  });

  // Dropzone
  const dz = $('#dropzone');
  const fileInput = $('#file-input');
  dz.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', (e) => {
    handleFiles(Array.from(e.target.files));
    fileInput.value = '';
  });
  ['dragenter', 'dragover'].forEach(evt => {
    dz.addEventListener(evt, (e) => { e.preventDefault(); dz.classList.add('dragover'); });
  });
  ['dragleave', 'drop'].forEach(evt => {
    dz.addEventListener(evt, (e) => { e.preventDefault(); dz.classList.remove('dragover'); });
  });
  dz.addEventListener('drop', (e) => {
    const files = Array.from(e.dataTransfer?.files || []);
    handleFiles(files);
  });

  // Chat input
  const input = $('#chat-input');
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  });
  input.addEventListener('input', autoGrowInput);
  $('#btn-send').addEventListener('click', handleSend);

  // Render buttons
  $('#btn-render-proxy').addEventListener('click', () => triggerRender('proxy'));
  $('#btn-render-final').addEventListener('click', () => triggerRender('final'));
  $('#btn-refresh-renders').addEventListener('click', refreshRendersList);

  // Notes
  $('#btn-show-notes').addEventListener('click', openNotesModal);

  // Mobile panel toggles
  $('#btn-left-panel').addEventListener('click', () => $('#left-panel').classList.toggle('open'));
  $('#btn-right-panel').addEventListener('click', () => $('#right-panel').classList.toggle('open'));

  // Modal close buttons + backdrop click
  $$('[data-modal-close]').forEach((b) => {
    b.addEventListener('click', () => {
      const modal = b.closest('.modal');
      if (modal) hideModal(modal.id);
    });
  });
  $$('.modal-backdrop').forEach((bd) => {
    bd.addEventListener('click', () => {
      const modal = bd.closest('.modal');
      if (modal) hideModal(modal.id);
    });
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') hideAllModals();
  });

  // Online/offline awareness for WS reconnect
  window.addEventListener('online', () => {
    if (state.wsState !== 'connected') connectWS();
  });
  window.addEventListener('offline', () => {
    setWsState('disconnected');
  });

  // Reconnect on tab focus (covers cases where the laptop slept)
  window.addEventListener('focus', () => {
    if (state.currentProjectId && state.wsState !== 'connected') connectWS();
  });
}

// ----------------------------------------------------------
// Boot
// ----------------------------------------------------------
async function boot() {
  bindEvents();
  // v1.4 P1-2: chat-status indicator. Lives in the DOM between the
  // chat log and the input row; ``createChatStatus`` keeps it in sync
  // with the WS event stream.
  const statusEl = document.querySelector('#chat-status');
  if (statusEl) state.chatStatus = createChatStatus(statusEl);
  // v1.4 P1-3: cost badge. Sits next to the chat-status pill;
  // ``createCostBadge`` keeps the dollar label in sync with the
  // agent's ``cost_update`` events.
  const costEl = document.querySelector('#cost-badge');
  if (costEl) state.costBadge = createCostBadge(costEl);
  await refreshProjects();
  if (state.currentProjectId) {
    await loadProjectState();
    connectWS();
  } else {
    setChatEnabled(false);
    setWsState('disconnected');
  }
  startEditGraphRefresh();
}

document.addEventListener('DOMContentLoaded', boot);

// Expose for debugging in the console.
window.OpenEdit = {
  state,
  api,
  connectWS,
  // Test-only hooks. The ``__`` prefix signals these are not part of
  // the public API; the frontend normalizers/transforms are exposed
  // here so Node-sandbox tests can call the real function in the
  // real IIFE closure (regex-extracting the function body and
  // re-evaluating it in a fresh ``Function`` would not see closure
  // state, so refactors that introduce cross-references between
  // normalizers would slip past the tests). Keep this list narrow:
  // add a hook only when there's a test that needs it.
  __testHooks: {
    normalizeAssets,
    normalizeEdits,
    normalizeTimeline,
    normalizeRenders,
    normalizeNotes,
    openAssetPreview,
    // v1.4 P1-2: chat-status state machine. Exposed so Node-sandbox
    // tests can drive it through a synthetic WS event sequence
    // without a real DOM (see ``tests/test_serve_chat_status.py``).
    createChatStatus,
    // v1.4 P1-3: cost badge state machine. Exposed so Node-sandbox
    // tests can drive the badge without a real DOM (see
    // ``tests/test_serve_cost_badge.py``).
    createCostBadge,
    // v1.4 P1-1: search-assets results panel renderer. Exposed so
    // Node-sandbox tests can drive the panel without a real DOM
    // (see ``tests/test_serve_search_assets.py``).
    appendSearchResults,
    // v1.4 P1-1: the chat sender (used by the Add-to-project button
    // in the search-assets panel). Exposed so the search-assets
    // test can verify the import message is sent.
    sendChatMessage,
  },
};

})();
