/* ============================================================
   app.js — Open Edit frontend entry point. ES module that
   wires the other modules (state, dom, api, assets, chat, ws)
   into the page and exposes a small ``window.OpenEdit``
   namespace for in-browser debugging plus the test hooks the
   Node-sandbox tests depend on.

   The split (state.js / dom.js / api.js / assets.js /
   chat.js / ws.js) was the v1.4 P2 "General UI flexibility &
   debugging pass" refactor — see ``.superpowers/sdd/task-6-*``.
   The 1500-line IIFE is gone; each module is focused on one
   concern. No bundler is involved; modern browsers load
   ``<script type="module">`` natively.
   ============================================================ */

import {
  state,
  normalizeAssets,
  normalizeEdits,
  normalizeNotes,
  normalizeRenders,
  normalizeTimeline,
  summarizeOpPayload,
} from './js/state.js';
import { $, $$, el, showToast, hideModal, showModal, hideAllModals, fmtBytes, fmtTime } from './js/dom.js';
import { api } from './js/api.js';
import { renderAssets, openAssetPreview } from './js/assets.js';
import {
  clearChatLog,
  appendUserMessage,
  createChatStatus,
  createCostBadge,
  sendChatMessage,
  appendSearchResults,
} from './js/chat.js';
import { connectWS, setWsState, setOnTurnDone, scheduleReconnect } from './js/ws.js';

// ----------------------------------------------------------
// Project selector
// ----------------------------------------------------------
export async function refreshProjects() {
  try {
    state.projects = await api.listProjects();
    renderProjectSelect();

    // If the saved project no longer exists, clear it.
    if (state.currentProjectId && !state.projects.some(p => p.id === state.currentProjectId)) {
      state.currentProjectId = null;
      try { localStorage.removeItem('open_edit.current_project_id'); } catch {}
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
  if (!sel) return;
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

export function selectProject(id) {
  if (id === state.currentProjectId) return;
  state.currentProjectId = id;
  if (id) {
    try { localStorage.setItem('open_edit.current_project_id', id); } catch {}
  } else {
    try { localStorage.removeItem('open_edit.current_project_id'); } catch {}
  }

  // Reset conversation on project switch (each project has its own convs).
  state.conversationId = null;
  try { localStorage.removeItem('open_edit.conversation_id'); } catch {}
  clearChatLog();

  $('#project-select').value = id || '';
  loadProjectState();
  connectWS();
}

// ----------------------------------------------------------
// Loading-state helpers (v1.4 P2)
//
// The asset list and the project switch both go through
// ``loadProjectState`` (which awaits ``api.getProjectState``).
// Before the response lands, the assets-list used to show
// whatever was there before — either the default "No assets
// yet" empty state from the HTML, or the previous project's
// stale data on a switch. Both feel like a flash of "nothing
// is happening." These helpers pin a visible spinner during
// the in-flight window so the user knows data is on its way.
// ----------------------------------------------------------
function setAssetsLoading(loading) {
  const list = $('#assets-list');
  if (!list) return;
  if (loading) {
    list.innerHTML = '';
    list.appendChild(el('div', { class: 'loading-state' }, [
      el('div', { class: 'spinner' }),
      el('span', {}, ['Loading assets…']),
    ]));
  }
  // When false: no-op here. Callers (renderAssets / clearAssetsList)
  // refill the list with the appropriate state.
}

function clearAssetsList() {
  const list = $('#assets-list');
  if (!list) return;
  list.innerHTML = '';
  list.appendChild(el('div', { class: 'empty-state' }, ['No assets yet.', el('br'), 'Upload one below.']));
}

// ----------------------------------------------------------
// Project state (left + right panels)
// ----------------------------------------------------------
export async function loadProjectState() {
  if (!state.currentProjectId) {
    state.currentProjectState = null;
    clearAssetsList();
    renderEditGraph([]);
    renderRendersList([]);
    renderNotesSummary({ pending: 0, list: [] });
    setChatEnabled(false);
    return;
  }
  setChatEnabled(true);
  // Show the loading state up front so the user knows the fetch is
  // in flight, not just an empty list. The next renderAssets() call
  // replaces the loading marker with the actual data.
  setAssetsLoading(true);
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
    // The fetch failed — clear the loading state so the list isn't
    // stuck on a spinner, and toast the actual reason. The user gets
    // an empty list (the standard "no assets" state) so the next
    // successful load has somewhere to render into.
    clearAssetsList();
    showToast(`Failed to load project: ${e.message}`, 'error');
  }
}

function renderEditGraph(edits) {
  const list = $('#edit-graph-list');
  if (!list) return;
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
  if (!div) return;
  if (!notes || !notes.pending) {
    div.textContent = 'No pending notes.';
  } else {
    div.textContent = `${notes.pending} pending note${notes.pending === 1 ? '' : 's'}`;
  }
}

function renderRendersList(renders) {
  const list = $('#renders-list');
  if (!list) return;
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

export async function refreshRendersList() {
  if (!state.currentProjectId) return;
  try {
    const renders = await api.listRenders(state.currentProjectId);
    renderRendersList(renders);
  } catch {
    // Silent fail — renders list is non-critical.
  }
}

// ----------------------------------------------------------
// Notes modal
// ----------------------------------------------------------
function openNotesModal() {
  const notes = normalizeNotes(state.currentProjectState || {});
  const list = $('#notes-list');
  if (!list) return;
  list.innerHTML = '';
  if (!notes.list.length) {
    list.appendChild(el('div', { class: 'empty-state' }, ['No notes yet.']));
  } else {
    for (const n of notes.list) {
      list.appendChild(el('div', { class: 'note-item' }, [
        el('div', { class: 'note-ts' }, [
          `[${fmtTime(n.timestamp)}] · ${n.source} · ${n.status}`,
        ]),
        el('div', { class: 'note-text' }, [n.text]),
      ]));
    }
  }
  showModal('modal-notes');
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
  } else {
    // v1.4 P2 review fix: the WS layer's onclose handler covers the
    // normal disconnect case, but if the user clicks Send while the
    // socket is stuck in CONNECTING (e.g. stalled TCP handshake or
    // browser tab throttling) onclose may never fire, leaving the
    // user stuck on the "Not connected. Retrying…" toast. Kick a
    // reconnect so the next attempt has a chance to land. Safe to
    // call when a reconnect is already pending — scheduleReconnect
    // is a no-op in that case (see ws.js).
    scheduleReconnect();
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

  // Wire the WS turn-done callback to refresh project state. This
  // keeps ws.js free of any dependency on the project-state loader
  // (avoids a circular import), while still letting the WS layer
  // call back into the UI when a turn ends.
  setOnTurnDone(() => {
    loadProjectState();
    refreshRendersList();
  });

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

// Expose for debugging in the console. The ``__testHooks`` namespace
// is what the Node-sandbox tests (test_serve_chat_status.py,
// test_serve_search_assets.py, test_serve_cost_badge.py,
// test_serve_asset_stream.py, etc.) drive. Keep the list narrow:
// add a hook only when there's a test that needs it.
window.OpenEdit = {
  state,
  api,
  connectWS,
  refreshProjects,
  loadProjectState,
  selectProject,
  __testHooks: {
    normalizeAssets,
    normalizeEdits,
    normalizeTimeline,
    normalizeRenders,
    normalizeNotes,
    summarizeOpPayload,
    openAssetPreview,
    // v1.4 P1-2: chat-status state machine.
    createChatStatus,
    // v1.4 P1-3: cost badge state machine.
    createCostBadge,
    // v1.4 P1-1: search-assets results panel renderer.
    appendSearchResults,
    // The chat sender (used by the Add-to-project button).
    sendChatMessage,
    // v1.4 P2 review fix: the click-path that handles the
    // CONNECTING-stuck edge case by kicking scheduleReconnect.
    // Test: tests/test_serve_send_reconnect.py.
    handleSend,
  },
};
