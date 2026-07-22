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
  createVerifyChip,
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
  loadLLMConfig();
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
    // Render the timeline panel if full timeline data is included
    if (s.timeline_full) {
      renderTimeline(s.timeline_full);
    }
  } catch (e) {
    // The fetch failed — clear the loading state so the list isn't
    // stuck on a spinner, and toast the actual reason. The user gets
    // an empty list (the standard "no assets" state) so the next
    // successful load has somewhere to render into.
    clearAssetsList();
    showToast(`Failed to load project: ${e.message}`, 'error');
  }
}

/** ID of the currently selected edit in the edit-graph panel */
let selectedEditId = null;

function renderEditGraph(edits) {
  const list = $('#edit-graph-list');
  if (!list) return;
  list.innerHTML = '';
  if (!edits.length) {
    list.appendChild(el('div', { class: 'empty-state' }, ['No edits yet.', el('br'), 'Ask the agent to do something.']));
    hideEditDetail();
    return;
  }
  // Show most recent first.
  for (const e of [...edits].reverse().slice(0, 50)) {
    const card = el('div', {
      class: 'edit-card' + (e.edit_id === selectedEditId ? ' edit-card-selected' : ''),
    }, [
      el('div', { class: 'edit-card-header' }, [
        el('span', { class: 'edit-kind' }, [e.kind]),
        e.status ? el('span', { class: 'edit-status edit-status-' + e.status }, [e.status]) : null,
        e.author ? el('span', { class: 'edit-author' }, [e.author]) : null,
      ]),
      el('div', { class: 'edit-summary' }, [e.summary || '—']),
    ]);
    card.addEventListener('click', () => selectEdit(e));
    list.appendChild(card);
  }
}

function selectEdit(e) {
  selectedEditId = e.edit_id;
  // Re-render to update selected state on all cards
  const edits = normalizeEdits(state.currentProjectState || {});
  renderEditGraph(edits);
  showEditDetail(e);
}

function showEditDetail(e) {
  const panel = $('#edit-detail-panel');
  if (!panel) return;
  panel.classList.remove('hidden');
  $('#edit-detail-kind').textContent = e.kind;
  $('#edit-detail-status').textContent = e.status || 'applied';
  $('#edit-detail-author').textContent = e.author || '—';
  $('#edit-detail-id').textContent = e.edit_id ? e.edit_id.slice(0, 12) + '…' : '—';

  // Build a readable payload summary
  const payloadEntries = [];
  if (e.payload && typeof e.payload === 'object') {
    for (const [k, v] of Object.entries(e.payload)) {
      if (k === 'edit_id' || k === 'parent_id' || k === 'author' || k === 'timestamp' || k === 'status') continue;
      payloadEntries.push(el('div', { class: 'edit-detail-field' }, [
        el('span', { class: 'edit-detail-key' }, [k]),
        el('span', { class: 'edit-detail-val' }, [JSON.stringify(v, null, 0).slice(0, 120)]),
      ]));
    }
  }
  const payloadDiv = $('#edit-detail-payload');
  payloadDiv.innerHTML = '';
  if (payloadEntries.length) {
    for (const entry of payloadEntries) payloadDiv.appendChild(entry);
  } else {
    payloadDiv.textContent = '—';
  }

  // Wire action buttons
  const btnUndo = $('#btn-edit-undo');
  const btnDelete = $('#btn-edit-delete');
  if (btnUndo) {
    btnUndo.disabled = e.status === 'reverted';
    btnUndo.onclick = () => undoEdit(e);
  }
  if (btnDelete) {
    btnDelete.onclick = () => deleteEdit(e);
  }
}

function hideEditDetail() {
  selectedEditId = null;
  const panel = $('#edit-detail-panel');
  if (panel) panel.classList.add('hidden');
}

async function undoEdit(e) {
  if (!state.currentProjectId) return;
  const newStatus = e.status === 'reverted' ? 'applied' : 'reverted';
  try {
    const r = await fetch(
      `/api/projects/${encodeURIComponent(state.currentProjectId)}/ops/${encodeURIComponent(e.edit_id)}/status`,
      { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: newStatus }) },
    );
    if (!r.ok) throw new Error((await r.json()).detail || `HTTP ${r.status}`);
    showToast(`${newStatus === 'reverted' ? 'Undid' : 'Redid'} ${e.kind}`, 'success');
    await loadProjectState();
  } catch (err) {
    showToast(`Failed to undo: ${err.message}`, 'error');
  }
}

async function deleteEdit(e) {
  if (!state.currentProjectId) return;
  if (!confirm(`Delete ${e.kind}? This cannot be undone.`)) return;
  try {
    const r = await fetch(
      `/api/projects/${encodeURIComponent(state.currentProjectId)}/ops/${encodeURIComponent(e.edit_id)}`,
      { method: 'DELETE' },
    );
    if (!r.ok) throw new Error((await r.json()).detail || `HTTP ${r.status}`);
    hideEditDetail();
    showToast(`Deleted ${e.kind}`, 'success');
    await loadProjectState();
  } catch (err) {
    showToast(`Failed to delete: ${err.message}`, 'error');
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
// Settings modal (BYOK & Runtime Discovery)
// ----------------------------------------------------------
async function openSettingsModal() {
  const rList = $('#settings-runtimes-list');
  if (rList) rList.textContent = 'Scanning PATH & GUI directories…';

  showModal('modal-settings');

  try {
    const [rRes, kRes] = await Promise.all([
      fetch('/api/runtimes').then(r => r.json()),
      fetch('/api/settings/keys').then(r => r.json()),
    ]);

    if (rList && rRes.runtimes) {
      rList.innerHTML = '';
      for (const rt of rRes.runtimes) {
        const statusBadge = rt.installed
          ? el('span', { style: 'color: var(--green); font-weight:600;' }, ['✓ Installed'])
          : el('span', { style: 'color: var(--text-dim);' }, ['— Not detected']);
        const pathText = rt.binary_path ? ` (${rt.binary_path})` : '';
        rList.appendChild(el('div', { class: 'note-item' }, [
          el('div', { style: 'display:flex; justify-content:space-between;' }, [
            el('strong', {}, [rt.name]),
            statusBadge,
          ]),
          rt.binary_path ? el('div', { class: 'muted small' }, [pathText]) : null,
        ]));
      }
    }

    if (kRes) {
      ['anthropic', 'openai', 'opencode', 'antigravity'].forEach(p => {
        const inp = $(`#key-${p}`);
        if (inp && kRes[p]) {
          inp.placeholder = kRes[p].has_key
            ? `Active (${kRes[p].source}): ${kRes[p].masked_key}`
            : `Enter ${p} API key…`;
          inp.value = '';
        }
      });
    }
  } catch (err) {
    showToast(`Failed to load settings: ${err.message}`, 'error');
  }
}

async function saveSettingsKeys() {
  const providers = ['anthropic', 'openai', 'opencode', 'antigravity'];
  let savedCount = 0;
  for (const p of providers) {
    const val = $(`#key-${p}`)?.value.trim();
    if (val) {
      try {
        await fetch('/api/settings/keys', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ provider: p, key: val }),
        });
        savedCount++;
      } catch (err) {
        console.error(`Save key failed for ${p}:`, err);
      }
    }
  }
  if (savedCount > 0) {
    showToast(`Saved ${savedCount} API key${savedCount === 1 ? '' : 's'} to ~/.open_edit/keys.json`, 'success');
    await loadLLMConfig();
  }
  hideModal('modal-settings');
}

// ----------------------------------------------------------
// Theme System (Dark / Light)
// ----------------------------------------------------------
function initTheme() {
  const saved = localStorage.getItem('open-edit-theme') || 'dark';
  applyTheme(saved);
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('open-edit-theme', theme);
  const btn = $('#btn-toggle-theme');
  if (btn) btn.textContent = theme === 'dark' ? '🌙' : '☀️';
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'dark';
  const next = current === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  showToast(`Switched to ${next} mode`, 'success');
}

// ----------------------------------------------------------
// Command Palette (Cmd+K / Ctrl+K)
// ----------------------------------------------------------
const COMMANDS = [
  { id: 'new-project', title: 'Create New Project', icon: '➕', action: () => $('#btn-new-project')?.click() },
  { id: 'refresh-projects', title: 'Refresh Projects List', icon: '⟳', action: () => refreshProjects() },
  { id: 'render-proxy', title: 'Render Proxy Video (540p)', icon: '🎬', action: () => triggerRender('proxy') },
  { id: 'render-final', title: 'Render Final Video (1080p)', icon: '🎥', action: () => triggerRender('final') },
  { id: 'open-settings', title: 'Open Settings & API Keys', icon: '⚙️', action: () => openSettingsModal() },
  { id: 'toggle-theme', title: 'Toggle Light / Dark Mode', icon: '🌓', action: () => toggleTheme() },
  { id: 'upload-assets', title: 'Upload Media Files', icon: '⬆', action: () => $('#file-input')?.click() },
  { id: 'clear-chat', title: 'Clear Chat Log', icon: '🗑️', action: () => clearChatLog() },
];

let activeCmdIndex = 0;
let filteredCommands = [...COMMANDS];

function openCmdPalette() {
  const modal = $('#modal-cmd-k');
  const input = $('#cmd-input');
  if (!modal || !input) return;
  input.value = '';
  filteredCommands = [...COMMANDS];
  activeCmdIndex = 0;
  renderCmdList();
  showModal('modal-cmd-k');
  setTimeout(() => input.focus(), 50);
}

function renderCmdList() {
  const list = $('#cmd-list');
  if (!list) return;
  list.innerHTML = '';
  if (!filteredCommands.length) {
    list.appendChild(el('div', { class: 'empty-state' }, ['No matching commands']));
    return;
  }
  filteredCommands.forEach((cmd, idx) => {
    const item = el('div', { class: `cmd-item ${idx === activeCmdIndex ? 'active' : ''}` }, [
      el('div', { class: 'cmd-item-label' }, [
        el('span', {}, [cmd.icon]),
        el('span', {}, [cmd.title]),
      ]),
      el('span', { class: 'kbd-badge' }, ['↵']),
    ]);
    item.addEventListener('click', () => executeCmd(cmd));
    list.appendChild(item);
  });
}

function executeCmd(cmd) {
  hideModal('modal-cmd-k');
  if (cmd && typeof cmd.action === 'function') {
    cmd.action();
  }
}

function handleCmdKeydown(e) {
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    if (filteredCommands.length) {
      activeCmdIndex = (activeCmdIndex + 1) % filteredCommands.length;
      renderCmdList();
    }
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    if (filteredCommands.length) {
      activeCmdIndex = (activeCmdIndex - 1 + filteredCommands.length) % filteredCommands.length;
      renderCmdList();
    }
  } else if (e.key === 'Enter') {
    e.preventDefault();
    if (filteredCommands[activeCmdIndex]) {
      executeCmd(filteredCommands[activeCmdIndex]);
    }
  }
}

function filterCmdList(query) {
  const q = query.toLowerCase().trim();
  if (!q) {
    filteredCommands = [...COMMANDS];
  } else {
    filteredCommands = COMMANDS.filter(c => c.title.toLowerCase().includes(q));
  }
  activeCmdIndex = 0;
  renderCmdList();
}


// ----------------------------------------------------------
// Chat input
// ----------------------------------------------------------
function setChatEnabled(enabled) {
  const input = $('#chat-input');
  const btnSend = $('#btn-send');
  const btnStop = $('#btn-stop');
  const btnTopbarStop = $('#btn-topbar-stop');
  if (input) input.disabled = !enabled;
  if (btnSend) {
    btnSend.disabled = !enabled;
    if (btnSend.classList && typeof btnSend.classList.toggle === 'function') {
      btnSend.classList.toggle('hidden', !enabled);
    }
  }
  if (btnStop) {
    if (btnStop.classList && typeof btnStop.classList.toggle === 'function') {
      btnStop.classList.toggle('hidden', enabled);
    }
  }
  if (btnTopbarStop) {
    if (btnTopbarStop.classList && typeof btnTopbarStop.classList.toggle === 'function') {
      btnTopbarStop.classList.toggle('hidden', enabled);
    }
  }
  if (enabled && input) input.focus();
}

function cancelTurn() {
  if (state.ws) {
    try {
      state.ws.send(JSON.stringify({ type: 'cancel' }));
    } catch {}
  }
  markTurnDone();
  if (state.chatStatus) state.chatStatus.onEvent({ type: 'done', stop_reason: 'cancelled' });
  setChatEnabled(true);
  showToast('Turn interrupted by user', 'warn');
}

function handleSend() {
  const input = $('#chat-input');
  const text = input.value.trim();
  if (!text) return;
  if (!state.currentProjectId) {
    showToast('Select or create a project first.', 'error');
    return;
  }
  setChatEnabled(false);
  if (sendChatMessage(text)) {
    appendUserMessage(text);
    input.value = '';
    autoGrowInput();
    if (state.chatStatus) state.chatStatus.send();
  } else {
    setChatEnabled(true);
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
      const edits = normalizeEdits(s);
      renderAssets(normalizeAssets(s.assets));
      renderEditGraph(edits);
      renderNotesSummary(normalizeNotes(s));
      // If an edit is selected, re-show its detail panel with fresh data
      if (selectedEditId) {
        const selected = edits.find(e => e.edit_id === selectedEditId);
        if (selected) showEditDetail(selected);
        else hideEditDetail();
      }
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
  $('#btn-stop')?.addEventListener('click', cancelTurn);
  $('#btn-topbar-stop')?.addEventListener('click', cancelTurn);

  // Render buttons
  $('#btn-render-proxy').addEventListener('click', () => triggerRender('proxy'));
  $('#btn-render-final').addEventListener('click', () => triggerRender('final'));
  $('#btn-refresh-renders').addEventListener('click', refreshRendersList);

  // Notes & Settings & Theme & Cmd+K
  $('#btn-show-notes').addEventListener('click', openNotesModal);
  $('#btn-settings').addEventListener('click', openSettingsModal);
  $('#btn-save-settings-keys').addEventListener('click', saveSettingsKeys);
  $('#btn-toggle-theme')?.addEventListener('click', toggleTheme);
  $('#btn-cmd-k')?.addEventListener('click', openCmdPalette);

  // Command palette inputs
  $('#cmd-input')?.addEventListener('input', (e) => filterCmdList(e.target.value));
  $('#cmd-input')?.addEventListener('keydown', handleCmdKeydown);

  // Quick Prompt Chips
  $$('.prompt-chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      const text = chip.dataset.prompt;
      const input = $('#chat-input');
      if (input && text) {
        input.value = text;
        handleSend();
      }
    });
  });

  // Global Keyboard Shortcuts (Cmd+K / Ctrl+K)
  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      openCmdPalette();
    }
  });

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
// LLM provider/model selection (v1.7)
//
// The selection bar lives in the topbar and lets the user pick the
// provider + model used for the next chat turn. The choice is
// persisted to ``<project>/.open_edit/config.toml`` via
// ``GET /api/projects/{id}/llm-config`` and
// ``PUT /api/projects/{id}/llm-config`` (see
// ``open_edit/serve/app.py``). After a save we reconnect the WS
// so the next turn picks up the new provider.
//
// We use ``fetch()`` directly because the existing ``api.js``
// module only ships dedicated methods (listProjects,
// getProjectState, …) — adding ``get``/``put`` would touch a
// file outside this task's scope. The pattern is otherwise the
// same as the dedicated helpers: throw an ``Error`` with the
// server's ``{"error": ...}`` payload so the toast shows the
// real reason.
// ----------------------------------------------------------
const llmProviderSelect = $('#llm-provider-select');
const llmModelSelect = $('#llm-model-select');
// v1.7 §6 A5: tools are triggered by the LLM via ``tool_use`` events
// (not by user clicks), so the ``#llm-tools-warn`` warning span is
// the sole tool-UI gating — no dedicated tool-trigger buttons exist.
const llmToolsWarn = $('#llm-tools-warn');

const ANTIGRAVITY_DEFAULT_MODEL = 'gemini-2.5-flash';
const TOOL_UNSUPPORTED_PROVIDERS = new Set([]);

async function fetchProviderModels(provider) {
  try {
    const r = await fetch(`/api/llm/providers/${encodeURIComponent(provider)}/models`);
    if (r.ok) {
      const data = await r.json();
      return data.models || [];
    }
  } catch { /* ignore */ }
  return [];
}

async function fetchLLMConfig(projectId) {
  const r = await fetch(`/api/projects/${encodeURIComponent(projectId)}/llm-config`);
  if (!r.ok) {
    let msg = `HTTP ${r.status}`;
    try {
      const body = await r.json();
      msg = body.error || body.detail || msg;
    } catch { /* ignore */ }
    throw new Error(msg);
  }
  return r.json();
}

async function putLLMConfigRequest(projectId, provider, model) {
  const r = await fetch(`/api/projects/${encodeURIComponent(projectId)}/llm-config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider, model }),
  });
  if (!r.ok) {
    let msg = `HTTP ${r.status}`;
    try {
      const body = await r.json();
      msg = body.error || body.detail || msg;
    } catch { /* ignore */ }
    throw new Error(msg);
  }
  return r.json();
}

export async function loadLLMConfig() {
  const projectId = state.currentProjectId;
  if (!projectId) {
    if (llmProviderSelect) llmProviderSelect.disabled = true;
    if (llmModelSelect) llmModelSelect.disabled = true;
    return;
  }
  try {
    const cfg = await fetchLLMConfig(projectId);
    populateProviderDropdown(cfg.available_providers, cfg.provider);
    populateModelDropdown(cfg.available_models, cfg.model);
    if (llmProviderSelect) llmProviderSelect.disabled = false;
    if (llmModelSelect) llmModelSelect.disabled = false;
    updateToolsWarning(cfg.provider);
  } catch (err) {
    console.error('loadLLMConfig failed', err);
    showToast(`Failed to load LLM config: ${err.message || err}`, 'error');
  }
}

function populateProviderDropdown(providers, current) {
  if (!llmProviderSelect) return;
  llmProviderSelect.innerHTML = '';
  const allProviders = (providers || []).slice().sort();
  for (const p of allProviders) {
    const opt = document.createElement('option');
    opt.value = p;
    opt.textContent = p;
    if (p === current) opt.selected = true;
    llmProviderSelect.appendChild(opt);
  }
}

function populateModelDropdown(models, current) {
  if (!llmModelSelect) return;
  llmModelSelect.innerHTML = '';
  if (!models || models.length === 0) {
    const opt = document.createElement('option');
    opt.value = current || 'default';
    opt.textContent = current || 'default';
    opt.selected = true;
    llmModelSelect.appendChild(opt);
    return;
  }
  let selectedFound = false;
  for (const m of models) {
    const opt = document.createElement('option');
    opt.value = m;
    opt.textContent = m;
    if (m === current) {
      opt.selected = true;
      selectedFound = true;
    }
    llmModelSelect.appendChild(opt);
  }
  if (!selectedFound && current) {
    const opt = document.createElement('option');
    opt.value = current;
    opt.textContent = current;
    opt.selected = true;
    llmModelSelect.appendChild(opt);
  }
}

function updateToolsWarning(provider) {
  if (!llmToolsWarn) return;
  if (TOOL_UNSUPPORTED_PROVIDERS.has(provider)) {
    llmToolsWarn.classList.remove('hidden');
  } else {
    llmToolsWarn.classList.add('hidden');
  }
}

async function saveLLMConfig(provider, model) {
  const projectId = state.currentProjectId;
  if (!projectId) return;
  try {
    const cfg = await putLLMConfigRequest(projectId, provider, model);
    populateProviderDropdown(cfg.available_providers, cfg.provider);
    populateModelDropdown(cfg.available_models, cfg.model);
    updateToolsWarning(cfg.provider);
    showToast(`LLM set to ${cfg.provider} / ${cfg.model}`, 'success');
    connectWS();
  } catch (err) {
    console.error('saveLLMConfig failed', err);
    showToast(`Failed to save LLM config: ${err.message || err}`, 'error');
  }
}

if (llmProviderSelect) {
  llmProviderSelect.addEventListener('change', async () => {
    const provider = llmProviderSelect.value;
    const models = await fetchProviderModels(provider);
    const firstModel = (models && models.length > 0) ? models[0] : '';
    await saveLLMConfig(provider, firstModel);
    await loadLLMConfig();
  });
}

if (llmModelSelect) {
  llmModelSelect.addEventListener('change', async () => {
    const provider = llmProviderSelect ? llmProviderSelect.value : '';
    const model = llmModelSelect.value;
    await saveLLMConfig(provider, model);
  });
}



// ----------------------------------------------------------
// Boot
// ----------------------------------------------------------
async function boot() {
  initTheme();
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
  // v1.5: verification chip. Sits next to the cost badge;
  // ``createVerifyChip`` keeps the per-render verify label in sync
  // with the agent's ``verification_started`` / ``verification_result``
  // events. Mirrors the chat-status / cost-badge wiring pattern.
  const verifyEl = document.querySelector('.verify-chip');
  if (verifyEl) state.verifyChip = createVerifyChip(verifyEl);

  // Wire the WS turn-done callback to refresh project state. This
  // keeps ws.js free of any dependency on the project-state loader
  // (avoids a circular import), while still letting the WS layer
  // call back into the UI when a turn ends.
  setOnTurnDone(async () => {
    await loadProjectState();
    refreshRendersList();
  });

  await refreshProjects();
  if (state.currentProjectId) {
    await loadProjectState();
    loadLLMConfig();
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

// ============================================================
// Timeline Panel (added: HTML Overlay support)
// ============================================================

/** Pixels per second at zoom=1 */
const TL_BASE_PPS = 60;
let tlZoom = 1.0;
let tlDurationSec = 0;
let tlCurrentData = null;

/** Convert seconds to pixels using current zoom level */
function secToPx(sec) { return sec * TL_BASE_PPS * tlZoom; }

/** Draw the seconds ruler */
function renderRuler(durationSec) {
  const ruler = $('#timeline-ruler');
  if (!ruler) return;
  ruler.innerHTML = '';
  const step = tlZoom < 0.5 ? 10 : tlZoom < 1.5 ? 5 : 2;
  const totalSec = Math.max(durationSec, 10);
  ruler.style.width = secToPx(totalSec) + 'px';
  for (let t = 0; t <= totalSec; t += step) {
    const tick = el('div', {
      class: 'timeline-ruler-tick',
      style: `left:${secToPx(t)}px`,
    }, [
      el('div', { class: 'timeline-ruler-tick-line' }),
      el('div', { class: 'timeline-ruler-tick-label' }, [`${t}s`]),
    ]);
    ruler.appendChild(tick);
  }
}

/** Main render function — draws tracks, clips, and overlay markers */
export function renderTimeline(timelineData) {
  tlCurrentData = timelineData;
  const labelsCol = $('#timeline-track-labels');
  const tracksArea = $('#timeline-tracks-area');
  const emptyMsg = $('#timeline-empty-msg');
  const durationLabel = $('#timeline-duration-label');
  if (!labelsCol || !tracksArea) return;

  const tracks = timelineData?.tracks ?? [];
  const overlays = timelineData?.overlays ?? [];
  const durationSec = timelineData?.duration_sec ?? 0;
  tlDurationSec = durationSec;

  if (durationLabel) {
    durationLabel.textContent = durationSec > 0
      ? `${durationSec.toFixed(1)}s`
      : '—';
  }

  // Clear previous content (keep the ruler header placeholder in labels)
  labelsCol.innerHTML = '<div class="timeline-track-label-row" style="height:20px;border-bottom:1px solid var(--border);"></div>';
  tracksArea.innerHTML = '';

  if (tracks.length === 0) {
    if (emptyMsg) tracksArea.appendChild(emptyMsg);
    emptyMsg && (emptyMsg.style.display = '');
    renderRuler(10);
    return;
  }
  if (emptyMsg) emptyMsg.style.display = 'none';

  renderRuler(Math.max(durationSec, 10));

  // Calculate total overlay height (one row per overlay track in the future;
  // for now, overlay markers live on top of all tracks)
  const totalWidth = secToPx(Math.max(durationSec, 10));

  tracks.forEach((track) => {
    // Label
    const kindBadge = el('span', {
      class: `track-kind-badge ${track.kind ?? 'video'}`,
    }, [track.kind === 'audio' ? '♪' : '▶']);
    const labelRow = el('div', { class: 'timeline-track-label-row' }, [
      kindBadge,
      document.createTextNode(track.track_id ?? ''),
    ]);
    labelsCol.appendChild(labelRow);

    // Track row
    const trackRow = el('div', { class: 'timeline-track-row', style: `min-width:${totalWidth}px` });

    // Clips
    (track.clips ?? []).forEach((clip) => {
      const clipDur = (clip.out_point_sec ?? 0) - (clip.in_point_sec ?? 0);
      const left = secToPx(clip.position_sec ?? 0);
      const width = Math.max(secToPx(clipDur), 4);
      const hashShort = (clip.asset_hash ?? '').slice(0, 8);
      const clipKind = track.kind === 'audio' ? 'audio-clip' : 'video-clip';
      const clipEl = el('div', {
        class: `timeline-clip ${clipKind}`,
        style: `left:${left}px;width:${width}px`,
        title: `${clip.clip_id ?? ''}\n${clip.asset_hash ?? ''}\n${clip.position_sec?.toFixed(2)}s → ${(clip.position_sec + clipDur).toFixed(2)}s`,
      }, [hashShort]);
      trackRow.appendChild(clipEl);
    });

    // Overlay markers on each track row
    overlays.forEach((ov) => {
      const left = secToPx(ov.position_sec ?? 0);
      const width = Math.max(secToPx(ov.duration_sec ?? 0), 4);
      const marker = el('div', {
        class: 'timeline-overlay-marker',
        style: `left:${left}px;width:${width}px`,
        title: `HTML Overlay: ${ov.template_path ?? ''}\n${JSON.stringify(ov.variables ?? {})}`,
      });
      trackRow.appendChild(marker);
    });

    tracksArea.appendChild(trackRow);
  });
}

// ---- Zoom controls ----
$('#btn-timeline-zoom-in')?.addEventListener('click', () => {
  tlZoom = Math.min(tlZoom * 1.5, 8);
  if (tlCurrentData) renderTimeline(tlCurrentData);
});
$('#btn-timeline-zoom-out')?.addEventListener('click', () => {
  tlZoom = Math.max(tlZoom / 1.5, 0.1);
  if (tlCurrentData) renderTimeline(tlCurrentData);
});
$('#btn-timeline-fit')?.addEventListener('click', () => {
  const col = $('#timeline-ruler-col');
  if (!col || !tlDurationSec) return;
  const availWidth = col.clientWidth - 20;
  tlZoom = availWidth / (tlDurationSec * TL_BASE_PPS);
  tlZoom = Math.max(0.05, Math.min(tlZoom, 8));
  if (tlCurrentData) renderTimeline(tlCurrentData);
});

// ---- Hook into loadProjectState ----
// Patch the existing loadProjectState to also call renderTimeline.
// We do this by wrapping the exported reference after initial load.
const _origLoadProjectState = loadProjectState;
window.__renderTimeline = renderTimeline;

// Called by WS messages or after state loads to refresh the timeline panel
export function refreshTimeline(rawState) {
  if (!rawState) return;
  const tl = rawState.timeline_full ?? rawState.timeline ?? null;
  if (tl) renderTimeline(tl);
}
