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
import { $, $$, el, icon, showToast, hideModal, showModal, hideAllModals, fmtBytes, fmtTime } from './js/dom.js';
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
  markTurnDone,
  setTurnActive,
} from './js/chat.js';
import { connectWS, disconnectWS, setReviewConnStatus, setWsState, setOnTurnDone, scheduleReconnect } from './js/ws.js';

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
    // Refresh the chat log to match the restored selection: the static
    // welcome markup is only valid when no project is selected — with a
    // saved project we must render the project-aware "Ready to edit"
    // state instead (round-4 B2).
    clearChatLog();
    refreshProjectDependentControls();
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
  state._autoSeedTimelineFor = null;
  if (id) {
    try { localStorage.setItem('open_edit.current_project_id', id); } catch {}
  } else {
    try { localStorage.removeItem('open_edit.current_project_id'); } catch {}
  }

  // Reset conversation on project switch (each project has its own convs).
  state.conversationId = null;
  try { localStorage.removeItem('open_edit.conversation_id'); } catch {}
  clearChatLog();

  // Reset right-panel state: edit detail, timeline, status widgets
  hideEditDetail();
  selectedEditId = null;
  const tracksArea = $('#timeline-tracks-area');
  const labelsCol = $('#timeline-track-labels');
  if (tracksArea) tracksArea.innerHTML = '';
  if (labelsCol) labelsCol.innerHTML = '';
  const ruler = $('#timeline-ruler');
  if (ruler) ruler.innerHTML = '';
  const durationLabel = $('#timeline-duration-label');
  if (durationLabel) durationLabel.textContent = '—';
  const emptyMsg = $('#timeline-empty-msg');
  if (emptyMsg) emptyMsg.classList.remove('hidden');
  if (state.chatStatus) state.chatStatus.reset();
  if (state.costBadge) state.costBadge.reset();
  if (state.verifyChip) state.verifyChip.reset();

  $('#project-select').value = id || '';
  loadProjectState();
  if (state.reviewOnly) {
    disconnectWS();
    setReviewConnStatus();
  } else {
    loadLLMConfig();
    connectWS();
  }
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

// Clear the source preview and transport when no project is selected so the
// home state never shows media from a deselected project (round-4 B3).
function clearSourcePreview() {
  state.previewRenderId = null;
  const player = $('#preview-player');
  if (player) {
    player.removeAttribute('src');
    player.src = '';
    player.load();
  }
  const empty = $('#preview-empty');
  if (empty) {
    empty.classList.remove('hidden');
    empty.style.display = '';
  }
  const badge = $('#preview-mode-badge');
  if (badge) badge.textContent = '—';
  const cur = $('#tc-current');
  if (cur) cur.textContent = '00:00.00';
  const total = document.querySelector('.transport-total');
  if (total) total.textContent = ' / —';
}

// ----------------------------------------------------------
// Project state (left + right panels)
// ----------------------------------------------------------
export async function loadProjectState() {
  refreshProjectDependentControls();
  if (!state.currentProjectId) {
    state.currentProjectState = null;
    clearAssetsList();
    renderEditGraph([]);
    renderRendersList([]);
    renderNotesSummary({ pending: 0, list: [] });
    clearSourcePreview();
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
    await paintProjectSnapshot(s);
  } catch (e) {
    // The fetch failed — clear the loading state so the list isn't
    // stuck on a spinner, and toast the actual reason. The user gets
    // an empty list (the standard "no assets" state) so the next
    // successful load has somewhere to render into.
    clearAssetsList();
    showToast(`Failed to load project: ${e.message}`, 'error');
  }
}

async function paintProjectSnapshot(s) {
  const assets = normalizeAssets(s.assets);
  renderAssets(assets, { onAddToTimeline: addAssetToTimeline });
  renderEditGraph(normalizeEdits(s));
  renderNotesSummary(normalizeNotes(s));
  const inlineRenders = normalizeRenders(s);
  if (inlineRenders) {
    renderRendersList(inlineRenders);
    maybeAutoLoadPreview(inlineRenders);
  } else {
    await refreshRendersList();
  }
  const timeline = normalizeTimeline(s.timeline_full ?? s.timeline);
  const newDur = Number(timeline.duration_sec || 0);
  if (Math.abs(newDur - tlDurationSec) > 0.5) tlAutoFitPending = false;
  renderTimeline(timeline, {
    edits: normalizeEdits(s),
    notes: normalizeNotes(s).list,
  });
  const hasClips = Number(timeline.clip_count || 0) > 0
    || (timeline.tracks ?? []).some((track) => (track.clips ?? []).length > 0);
  if (assets.length && !hasClips && state._autoSeedTimelineFor !== state.currentProjectId) {
    state._autoSeedTimelineFor = state.currentProjectId;
    const firstAsset = assets.find((asset) => {
      const mediaType = String(
        asset.type || asset.mime_type || asset.mime || asset.media_type
          || asset.extra?.type || asset.extra?.mime_type || asset.extra?.mime
          || asset.extra?.media_type || '',
      ).toLowerCase();
      return mediaType === 'video' || mediaType.startsWith('video/');
    }) || assets[0];
    addAssetToTimeline(firstAsset);
    return;
  }
  maybeLoadSourcePreview(s);
  if (s.timeline_status === 'invalid') {
    showToast(`Timeline invalid: ${s.timeline_error_code || 'derivation failed'}`, 'warn');
  }
}

async function addAssetToTimeline(asset) {
  if (!state.currentProjectId || !asset?.hash) return;
  const expectedRevision = state.currentProjectState?.graph_revision;
  const positionSec = Number(state.currentProjectState?.timeline?.total_duration_s || 0);
  try {
    const result = await api.applyTimelineCommand(
      state.currentProjectId,
      'add_clip',
      {
        asset_hash: asset.hash,
        track_id: 'V1',
        position_sec: positionSec,
        in_point_sec: 0,
        out_point_sec: asset.duration_s || null,
      },
      expectedRevision,
    );
    showToast(`Added ${asset.filename || 'clip'} to V1`, 'success');
    await loadProjectState();
  } catch (err) {
    showToast(`Add to timeline failed: ${err.message}`, 'error');
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

  // Build a readable payload summary (round-4 B6: stacked key/value cards,
  // truncated long hashes with a copy affordance instead of a debug dump).
  const payloadEntries = [];
  if (e.payload && typeof e.payload === 'object') {
    for (const [k, v] of Object.entries(e.payload)) {
      if (k === 'edit_id' || k === 'parent_id' || k === 'author' || k === 'timestamp' || k === 'status') continue;
      let raw = JSON.stringify(v, null, 0);
      const isLong = raw.length > 60;
      const shown = isLong ? raw.slice(0, 56) + '…' : raw;
      const valEl = el('span', { class: 'edit-detail-val' }, [shown]);
      if (isLong) {
        valEl.appendChild(el('button', {
          class: 'copy-hash',
          type: 'button',
          title: 'Copy full value',
          'aria-label': `Copy ${k}`,
        }, ['copy']));
        valEl.querySelector('.copy-hash').addEventListener('click', (ev) => {
          ev.stopPropagation();
          try { navigator.clipboard.writeText(raw); showToast('Copied to clipboard', 'success'); } catch {}
        });
      }
      payloadEntries.push(el('div', { class: 'edit-detail-field' }, [
        el('span', { class: 'edit-detail-key' }, [k]),
        valEl,
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
  const expectedRevision = state.currentProjectState?.graph_revision;
  try {
    const r = await fetch(
      `/api/projects/${encodeURIComponent(state.currentProjectId)}/ops/${encodeURIComponent(e.edit_id)}/status`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus, expected_revision: expectedRevision }),
      },
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
  if (!confirm(`Revert ${e.kind}? The operation stays in history as reverted.`)) return;
  const expectedRevision = state.currentProjectState?.graph_revision;
  try {
    const q = expectedRevision != null ? `?expected_revision=${encodeURIComponent(expectedRevision)}` : '';
    const r = await fetch(
      `/api/projects/${encodeURIComponent(state.currentProjectId)}/ops/${encodeURIComponent(e.edit_id)}${q}`,
      { method: 'DELETE' },
    );
    if (!r.ok) throw new Error((await r.json()).detail || `HTTP ${r.status}`);
    hideEditDetail();
    showToast(`Reverted ${e.kind}`, 'success');
    await loadProjectState();
  } catch (err) {
    showToast(`Failed to revert: ${err.message}`, 'error');
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

function setRenderButtonsBusy(busy, label) {
  for (const id of ['btn-render-proxy', 'btn-render-final']) {
    const btn = $(`#${id}`);
    if (!btn) continue;
    if (!btn.dataset.origLabel) btn.dataset.origLabel = btn.textContent;
    btn.disabled = !!busy;
    btn.textContent = busy && label ? label : btn.dataset.origLabel;
  }
}

/**
 * Convert worker diagnostics into short, structured UI labels.
 *
 * Preview diagnostics intentionally consume only bounded counters, ranges,
 * timings, and byte totals.  Paths and arbitrary nested worker data are not
 * copied into the browser-visible labels.
 */
export function formatPreviewDiagnostics(raw) {
  const diagnostics = raw?.diagnostics && typeof raw.diagnostics === 'object'
    ? raw.diagnostics
    : (raw && typeof raw === 'object' ? raw : {});
  const counts = diagnostics.counts && typeof diagnostics.counts === 'object'
    ? diagnostics.counts
    : {};
  const elapsed = diagnostics.elapsed_sec && typeof diagnostics.elapsed_sec === 'object'
    ? diagnostics.elapsed_sec
    : {};
  const bytes = diagnostics.bytes_written && typeof diagnostics.bytes_written === 'object'
    ? diagnostics.bytes_written
    : {};
  const cache = diagnostics.cache && typeof diagnostics.cache === 'object'
    ? diagnostics.cache
    : {};
  const evictions = diagnostics.evictions && typeof diagnostics.evictions === 'object'
    ? diagnostics.evictions
    : {};
  const number = (value) => Number.isFinite(Number(value)) ? Number(value) : 0;
  const seconds = (value) => `${number(value).toFixed(2)}s`;
  const ranges = Array.isArray(diagnostics.selected_ranges)
    ? diagnostics.selected_ranges
      .filter((range) => range && Number.isFinite(Number(range.start_sec))
        && Number.isFinite(Number(range.end_sec)))
      .map((range) => `${number(range.start_sec).toFixed(2)}–${number(range.end_sec).toFixed(2)}s`)
    : [];
  const stateLabel = diagnostics.graph_changed
    ? 'Graph changed'
    : diagnostics.partial
      ? 'Partial'
      : 'Ready';
  return {
    counts: `Chunks ${number(counts.selected_chunks)}/${number(counts.total_chunks)}`,
    ranges: `Ranges ${ranges.length ? ranges.join(', ') : 'none'}`,
    skipped_green: `Skipped green ${number(counts.skipped_green)}`,
    elapsed: `Video ${seconds(elapsed.video)} · Audio ${seconds(elapsed.audio)} · Mux ${seconds(elapsed.mux)}`,
    bytes: `Bytes ${fmtBytes(number(bytes.video))} video · ${fmtBytes(number(bytes.audio))} audio · ${fmtBytes(number(bytes.mux))} mux`,
    cache: `Cache ${number(cache.hits)} hits / ${number(cache.misses)} misses`,
    evictions: `Evictions ${number(evictions.removed_files)} files · ${fmtBytes(number(evictions.removed_bytes))}`,
    state: stateLabel,
  };
}

function renderRendersList(renders) {
  const list = $('#renders-list');
  if (!list) return;
  list.innerHTML = '';
  if (!renders.length) {
    list.appendChild(el('div', { class: 'empty-state' }, ['No renders yet.']));
    return;
  }
  const active = renders.some(r => r.status === 'queued' || r.status === 'running');
  setRenderButtonsBusy(active, active ? 'Rendering…' : null);
  // Newest first.
  for (const r of [...renders].reverse()) {
    const name = (r.path || '').split('/').pop() || r.id?.slice(0, 8) || 'render';
    const modeLabel = r.mode === 'final'
      ? 'Final export · 1080p'
      : (r.mode === 'proxy' ? 'Review artifact · 640×360' : r.mode || 'proxy');
    const status = r.status || 'succeeded';
    const statusLabel = status === 'running' ? 'Rendering…'
      : status === 'queued' ? 'Queued'
      : status === 'failed' ? `Failed: ${r.error || 'error'}`
      : status === 'succeeded' ? 'Ready'
      : status;
    const item = el('div', { class: `render-card render-status-${status}` }, [
      el('div', { class: 'render-thumb' }, [icon(status === 'running' || status === 'queued' ? 'hourglass' : 'film')]),
      el('div', { class: 'render-meta' }, [
        el('div', { class: 'render-name' }, [name]),
        el('div', { class: 'render-sub' }, [
          modeLabel,
          ' · ',
          statusLabel,
          r.size_bytes ? ` · ${fmtBytes(r.size_bytes)}` : '',
          r.timestamp ? ` · ${fmtTime(r.timestamp)}` : '',
        ]),
      ]),
    ]);
    item.addEventListener('click', () => {
      if (status !== 'succeeded') {
        showToast(status === 'running' || status === 'queued'
          ? 'Render still in progress — check back in a few minutes.'
          : (r.error || 'Render not available'), 'info');
        return;
      }
      if (r.id && state.currentProjectId) {
        loadRenderInPreview(r.id, r.mode || 'proxy');
        return;
      }
      if (r.path && /^https?:/.test(r.path)) {
        window.open(r.path, '_blank');
      } else if (r.path) {
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
    const active = renders.some(r => r.status === 'queued' || r.status === 'running');
    if (active && !state.renderPollTimer) {
      state.renderPollTimer = setInterval(() => refreshRendersList(), 5000);
    } else if (!active && state.renderPollTimer) {
      clearInterval(state.renderPollTimer);
      state.renderPollTimer = null;
      setRenderButtonsBusy(false);
    }
    maybeAutoLoadPreview(renders);
    const warn = $('#renders-degraded-warn');
    if (warn) warn.classList.add('hidden');
  } catch (err) {
    let warn = $('#renders-degraded-warn');
    if (!warn) {
      const list = $('#renders-list');
      warn = el('div', { id: 'renders-degraded-warn', class: 'empty-state' }, []);
      if (list && list.parentElement) list.parentElement.insertBefore(warn, list);
    }
    warn.classList.remove('hidden');
    warn.textContent = `Render list unavailable: ${err.message || err}`;
    showToast(`Render list unavailable: ${err.message || err}`, 'error');
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
          // Note timestamps are playhead anchors (seconds in the timeline), so
          // show them as timecodes — not as wall-clock dates.
          `[${formatTimecode(Number(n.timestamp) || 0)}] · ${n.source} · ${n.status}`,
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

  // Review-only mode gates these endpoints (404 by design); don't fetch them.
  if (document.body.classList.contains('review-only-mode')) {
    if (rList) {
      rList.innerHTML = '';
      rList.appendChild(el('div', { class: 'note-item muted small' }, [
        'Review mode: agent runtimes & API keys are managed by the agent harness. ' +
        'Start the server without --review-only to configure them here.',
      ]));
    }
    return;
  }

  try {
    const [rRes, kRes] = await Promise.all([
      fetch('/api/runtimes').then(r => r.json()),
      fetch('/api/settings/keys').then(r => r.json()),
    ]);

    if (rList && rRes.runtimes) {
      rList.innerHTML = '';
      for (const rt of rRes.runtimes) {
        const statusBadge = rt.installed
          ? el('span', { class: 'dep-status dep-status-ok' }, [icon('check'), 'Installed'])
          : el('span', { class: 'dep-status dep-status-missing' }, ['Not detected']);
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
        const r = await fetch('/api/settings/keys', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ provider: p, key: val }),
        });
        if (!r.ok) {
          const body = await r.json().catch(() => ({}));
          throw new Error(body.detail || `HTTP ${r.status}`);
        }
        savedCount++;
      } catch (err) {
        showToast(`Failed to save ${p} key: ${err.message}`, 'error');
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
  if (btn) btn.innerHTML = theme === 'dark'
    ? '<svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M21 12.8A8.5 8.5 0 1 1 11.2 3 6.7 6.7 0 0 0 21 12.8Z"></path></svg>'
    : '<svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="3.5" fill="none" stroke="currentColor" stroke-width="1.8"></circle><path d="M12 2v2.2M12 19.8V22M4.93 4.93l1.56 1.56M17.51 17.51l1.56 1.56M2 12h2.2M19.8 12H22M4.93 19.07l1.56-1.56M17.51 6.49l1.56-1.56" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"></path></svg>';
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
  { id: 'new-project', title: 'Create New Project', icon: 'plus', action: () => $('#btn-new-project')?.click() },
  { id: 'refresh-projects', title: 'Refresh Projects List', icon: 'refresh', action: () => refreshProjects() },
  { id: 'render-proxy', title: 'Render review artifact (640×360)', icon: 'film', action: () => triggerRender('proxy') },
  { id: 'render-final', title: 'Render Final Video (1080p)', icon: 'video', action: () => triggerRender('final') },
  { id: 'open-settings', title: 'Open Settings & API Keys', icon: 'settings', action: () => openSettingsModal() },
  { id: 'toggle-theme', title: 'Toggle Light / Dark Mode', icon: 'moon', action: () => toggleTheme() },
  { id: 'upload-assets', title: 'Upload Media Files', icon: 'upload', action: () => $('#file-input')?.click() },
  { id: 'clear-chat', title: 'Clear Chat Log', icon: 'trash', action: () => clearChatLog() },
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
        icon(cmd.icon),
        el('span', {}, [cmd.title]),
      ]),
      el('span', { class: 'kbd-badge' }, [icon('enter')]),
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
let chatBaseEnabled = false;
let sendDisabledReason = '';

function refreshSendGate() {
  const input = $('#chat-input');
  const btnSend = $('#btn-send');
  const provider = llmProviderSelect?.value || '';
  const model = llmModelSelect?.value || '';
  const capability = providerCapabilities.get(provider);
  let reason = '';
  if (!chatBaseEnabled) {
    reason = 'Select a project and connect chat first.';
  } else if (!provider) {
    reason = 'Select an LLM provider.';
  } else if (!model) {
    reason = 'Select a model for the current provider.';
  } else if (!capability) {
    reason = `Provider ${provider} is unavailable.`;
  }
  sendDisabledReason = reason;
  const enabled = !reason;
  if (input) input.disabled = !enabled;
  if (btnSend) {
    btnSend.disabled = !enabled;
    btnSend.title = reason || 'Send message';
    if (btnSend.classList && typeof btnSend.classList.toggle === 'function') {
      btnSend.classList.toggle('hidden', !chatBaseEnabled);
    }
  }
}

function setChatEnabled(enabled) {
  chatBaseEnabled = !!enabled;
  const input = $('#chat-input');
  refreshSendGate();
  // Stop buttons are owned by setTurnActive (round-4 B5): they must only
  // appear while a turn is running, not merely because chat is disabled.
  if (enabled && input && !input.disabled) input.focus();
}

// Round-5 C4: project-dependent controls (render encoder/buttons, LLM selects)
// must reflect whether a project exists, not just guard on click.
function refreshProjectDependentControls() {
  const hasProject = !!state.currentProjectId;
  const encoderSel = $('#render-encoder-select');
  const proxyBtn = $('#btn-render-proxy');
  const finalBtn = $('#btn-render-final');
  if (encoderSel) {
    encoderSel.disabled = !hasProject;
    encoderSel.title = hasProject ? '' : 'Select a project first';
  }
  for (const btn of [proxyBtn, finalBtn]) {
    if (!btn) continue;
    btn.disabled = !hasProject;
    btn.title = hasProject ? '' : 'Select a project first';
  }
  if (llmProviderSelect) {
    llmProviderSelect.disabled = !hasProject;
    llmProviderSelect.title = hasProject ? '' : 'Select a project first';
  }
  if (llmModelSelect) {
    llmModelSelect.disabled = !hasProject;
    llmModelSelect.title = hasProject ? '' : 'Select a project first';
  }
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
  sendText(text);
  input.value = '';
  autoGrowInput();
}

// The single path every user-originated message takes (chat input,
// search-result "Add to project", prompt chips). Locks the input,
// shows the user's bubble, activates the status pill.
function sendText(text) {
  if (!text) return;
  if (!state.currentProjectId) {
    showToast('Select or create a project first.', 'error');
    return;
  }
  setChatEnabled(false);
  if (sendChatMessage(text)) {
    appendUserMessage(text);
    if (state.chatStatus) state.chatStatus.send();
    setTurnActive(true);
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
  const detail = el('div', { class: 'upload-detail' }, []);
  prog.appendChild(detail);

  try {
    const result = await api.ingestFiles(state.currentProjectId, files, (p) => {
      bar.querySelector('.bar-fill').style.width = `${Math.round(p * 100)}%`;
    });
    const accepted = result.accepted || [];
    const rejected = result.rejected || [];
    detail.innerHTML = '';
    for (const a of accepted) {
      detail.appendChild(el('div', { class: 'upload-success' }, [icon('check'), a.filename || a.hash || 'file']));
    }
    for (const r of rejected) {
      detail.appendChild(el('div', { class: 'upload-error' }, [icon('close'), `${r.filename || 'file'}: ${r.error || 'rejected'}`]));
    }
    prog.querySelector('div').textContent =
      `Ingested ${accepted.length}/${files.length}` +
      (rejected.length ? ` (${rejected.length} rejected)` : '');
    if (accepted.length) {
      showToast(`Ingested ${accepted.length} file${accepted.length === 1 ? '' : 's'}`, 'success');
    }
    if (rejected.length) {
      showToast(`${rejected.length} file${rejected.length === 1 ? '' : 's'} rejected`, 'error');
    }
    await loadProjectState();
  } catch (e) {
    prog.querySelector('div').textContent = `Upload failed: ${e.message}`;
    showToast(`Upload failed: ${e.message}`, 'error');
  } finally {
    setTimeout(() => prog.classList.add('hidden'), 5000);
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
  const encoderSel = $('#render-encoder-select');
  const encoder = (encoderSel?.value === 'cpu') ? 'cpu' : 'gpu';
  if (mode === 'final') {
    const stale = await isProxyStale();
    if (stale) {
      const ok = confirm(
        'No proxy render matches the current edit graph. Render a proxy first to review, or continue with final anyway?',
      );
      if (!ok) return;
    }
  }
  showToast(`Rendering ${mode} on ${encoder.toUpperCase()}…`, 'info');
  setRenderButtonsBusy(true, 'Rendering…');
  if (mode === 'proxy') state.proxyRenderInFlight = true;
  try {
    const expectedRevision = state.currentProjectState?.graph_revision;
    const r = await fetch(`/api/projects/${encodeURIComponent(state.currentProjectId)}/render`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode, encoder, expected_revision: expectedRevision }),
    });
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      throw new Error(body.detail || body.error || `HTTP ${r.status}`);
    }
    const job = await r.json();
    refreshRendersList();
    pollRenderJob(job.job_id, mode);
  } catch (e) {
    setRenderButtonsBusy(false);
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
      if (job.status === 'succeeded') {
        showToast(`Render complete: ${job.output_path || '(output)'}`, 'success');
        refreshRendersList();
        if (mode === 'proxy') state.proxyRenderInFlight = false;
        loadRenderInPreview(job.job_id, mode);
        return;
      }
      if (['failed', 'cancelled', 'orphaned'].includes(job.status)) {
        showToast(`Render failed: ${job.error || 'unknown'}`, 'error');
        if (mode === 'proxy') state.proxyRenderInFlight = false;
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
      const prevRev = state.currentProjectState?.graph_revision;
      state.currentProjectState = s;
      // Skip full UI repaint when the graph revision is unchanged.
      if (prevRev != null && s.graph_revision === prevRev) return;
      if (prevRev != null && s.graph_revision !== prevRev) {
        showToast('Edit graph updated — render proxy to preview changes.', 'info');
        if (state.autoProxy && !state.proxyRenderInFlight) {
          // Debounce auto-proxy storms across rapid graph_revision bumps.
          clearTimeout(state._autoProxyDebounce);
          state._autoProxyDebounce = setTimeout(() => {
            if (!state.proxyRenderInFlight) triggerRender('proxy');
          }, 15000);
        }
      }
      await paintProjectSnapshot(s);
      const edits = normalizeEdits(s);
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
  $('#btn-copy-timecode')?.addEventListener('click', copyPlayheadTimecode);
  $('#btn-add-note-playhead')?.addEventListener('click', addNoteAtPlayhead);

  const previewPlayer = $('#preview-player');
  if (previewPlayer) {
    previewPlayer.addEventListener('timeupdate', () => {
      state.playheadSec = previewPlayer.currentTime || 0;
      updatePlayheadUi();
    });
    previewPlayer.addEventListener('loadedmetadata', updatePlayheadUi);
    previewPlayer.addEventListener('play', updatePreviewTransport);
    previewPlayer.addEventListener('pause', updatePreviewTransport);
    previewPlayer.addEventListener('ended', updatePreviewTransport);
  }
  // Keep the redesign's transport controls as a thin layer over the native
  // video element; native controls remain enabled for accessibility/fallback.
  $('#btn-skip-back')?.addEventListener('click', () => seekPreviewBy(-5));
  $('#btn-play')?.addEventListener('click', togglePreviewPlayback);
  $('#btn-skip-fwd')?.addEventListener('click', () => seekPreviewBy(5));

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

  // Quick-send requests from auxiliary widgets (search-result "Add to
  // project" buttons). Routed through the same path as the chat input
  // so the turn is visible and the input locks while it runs.
  document.addEventListener('open-edit:quick-send', (e) => {
    const text = e.detail && e.detail.text;
    if (text) sendText(text);
  });

  // Mobile panel toggles
  $('#btn-left-panel').addEventListener('click', () => $('#left-panel').classList.toggle('open'));
  $('#btn-right-panel').addEventListener('click', () => $('#right-panel').classList.toggle('open'));
  $('#btn-toggle-left-panel')?.addEventListener('click', () => {
    document.body.classList.toggle('panel-left-collapsed');
  });
  $('#btn-toggle-right-panel')?.addEventListener('click', () => {
    document.body.classList.toggle('panel-right-collapsed');
  });

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
    if (!state.reviewOnly && state.wsState !== 'connected') connectWS();
  });
  window.addEventListener('offline', () => {
    if (!state.reviewOnly) setWsState('disconnected');
  });

  // Reconnect on tab focus (covers cases where the laptop slept)
  window.addEventListener('focus', () => {
    if (!state.reviewOnly && state.currentProjectId && state.wsState !== 'connected') connectWS();
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
let providerCapabilities = new Map();

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
  if (!projectId || state.reviewOnly) {
    if (llmProviderSelect) llmProviderSelect.disabled = true;
    if (llmModelSelect) llmModelSelect.disabled = true;
    return;
  }
  try {
    const cfg = await fetchLLMConfig(projectId);
    providerCapabilities = new Map((cfg.provider_capabilities || []).map(p => [p.id, p]));
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
    const capability = providerCapabilities.get(p);
    const modeLabel = capability?.agent_mode === 'openedit_loop'
      ? 'Full editing agent'
      : capability?.agent_mode === 'external_loop'
        ? 'Full editing agent (external)'
        : 'Chat only';
    opt.textContent = `${capability?.label || p} — ${modeLabel}`;
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
  if (providerCapabilities.get(provider)?.agent_mode === 'chat_only') {
    llmToolsWarn.classList.remove('hidden');
  } else {
    llmToolsWarn.classList.add('hidden');
  }
  refreshSendGate();
}

async function saveLLMConfig(provider, model) {
  const projectId = state.currentProjectId;
  if (!projectId) return;
  try {
    const cfg = await putLLMConfigRequest(projectId, provider, model);
    providerCapabilities = new Map((cfg.provider_capabilities || []).map(p => [p.id, p]));
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
    if (!firstModel) {
      showToast(`No models available for ${provider}`, 'warn');
      return;
    }
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
  try {
    const cfg = await api.getUiConfig();
    state.reviewOnly = !!cfg.review_only;
    state.autoProxy = !!cfg.auto_proxy;
    if (state.reviewOnly) {
      document.body.classList.add('review-only-mode', 'panel-left-collapsed');
    }
  } catch {
    state.reviewOnly = false;
  }
  // Mode badge: announce the real running mode instead of the static
  // default text (data-review-label / data-agent-label live in the
  // index.html markup). Presentation-only.
  const modeLabelNode = document.querySelector('#mode-label');
  if (modeLabelNode) {
    modeLabelNode.textContent = state.reviewOnly
      ? (modeLabelNode.dataset.reviewLabel || 'Review \u00b7 MCP')
      : (modeLabelNode.dataset.agentLabel || 'Agent \u00b7 built-in');
  }
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
    if (!state.reviewOnly) {
      loadLLMConfig();
      connectWS();
    } else {
      disconnectWS();
      setReviewConnStatus();
    }
  } else {
    refreshProjectDependentControls();
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
  formatPreviewDiagnostics,
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
// Review studio: preview player + timeline playhead
// ============================================================

function formatTimecode(sec) {
  const s = Math.max(0, Number(sec) || 0);
  if (s >= 3600) {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const r = s % 60;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${r.toFixed(2).padStart(5, '0')}`;
  }
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${String(m).padStart(2, '0')}:${r.toFixed(2).padStart(5, '0')}`;
}

/** Play the source asset only when no proxy render exists yet. */
function maybeLoadSourcePreview(s) {
  if (!state.currentProjectId) return;
  const player = $('#preview-player');
  const empty = $('#preview-empty');
  if (!player) return;
  // Prefer proxy/final renders — never replace them with the raw source.
  if (state.previewRenderId && player.src) return;
  const renders = normalizeRenders(s) || [];
  if (renders.some((r) => r.status === 'succeeded' && (r.mode === 'proxy' || r.mode === 'final'))) {
    return;
  }

  const tl = normalizeTimeline(s?.timeline_full ?? s?.timeline);
  const assets = normalizeAssets(s?.assets || []);
  const firstClip = (tl?.tracks ?? []).flatMap((t) => t.clips ?? [])[0];
  const assetHash = firstClip?.asset_hash || assets[0]?.hash;
  if (!assetHash) return;

  const asset = assets.find((a) => a.hash === assetHash);
  const url = asset?.url
    || `/api/projects/${encodeURIComponent(state.currentProjectId)}/assets/${encodeURIComponent(assetHash)}/file`;

  state.previewRenderId = null;
  player.setAttribute('src', url);
  player.src = url;
  player.style.display = 'block';
  player.load();
  if (empty) {
    empty.classList.add('hidden');
    empty.style.display = 'none';
  }
  const badge = $('#preview-mode-badge');
  if (badge) badge.textContent = 'Source media';
  player.onloadeddata = () => {
    if (empty) {
      empty.classList.add('hidden');
      empty.style.display = 'none';
    }
  };
  player.onerror = () => {
    showToast('Source preview failed to load — try Render proxy after installing Shotcut/melt', 'error');
  };
}

function _isPlayableRender(r) {
  if (!r || r.status !== 'succeeded') return false;
  const id = String(r.id || '');
  const path = String(r.path || '');
  // Never auto-load melt intermediates (in-progress proxy writes).
  if (id.includes('.melt') || path.includes('.melt.')) return false;
  return true;
}

async function _renderEndpointIsReachable(render) {
  const renderId = render?.id;
  if (!state.currentProjectId || !renderId) return false;
  // The API rejects files outside the active project root.  Skip those stale
  // durable rows locally so probing them does not create a browser 404 log.
  // Rows without an absolute path still get the bounded URL probe because
  // the server may resolve them from its durable job table.
  const projectPath = String(state.currentProjectState?.path || '').replace(/\/+$/, '');
  const renderPath = String(render?.path || '');
  if (projectPath && renderPath && renderPath.startsWith('/')
      && !(renderPath === projectPath || renderPath.startsWith(`${projectPath}/`))) {
    return false;
  }
  try {
    // Probe with a one-byte range before assigning <video>.  A project can
    // contain durable rows whose output was produced in another checkout;
    // loading those rows would otherwise create a noisy 404 and strand the
    // preview until the user manually picks an older file-backed render.
    const response = await fetch(api.renderFileUrl(state.currentProjectId, renderId), {
      headers: { Range: 'bytes=0-0' },
      cache: 'no-store',
    });
    try { await response.body?.cancel(); } catch { /* probe only */ }
    return response.ok;
  } catch {
    return false;
  }
}

async function maybeAutoLoadPreview(renders) {
  if (!state.reviewOnly || !state.currentProjectId || !renders?.length) return;
  const player = $('#preview-player');
  if (!player) return;
  // list_renders returns jobs newest-first — do NOT reverse before find.
  const playable = renders.filter(_isPlayableRender);
  const currentHash = state.currentProjectState?.edit_graph_hash;
  const currentRev = state.currentProjectState?.graph_revision;
  const matchingHash = currentHash && playable.find(
    (r) => r.edit_graph_hash === currentHash && (r.mode === 'proxy' || r.mode === 'final'),
  );
  const matchingRev = (currentRev != null) && playable.find(
    (r) => r.graph_revision === currentRev && r.mode === 'proxy',
  );
  // Prefer newest job by graph_revision / timestamp — never the largest old file.
  const byRev = [...playable]
    .filter((r) => r.mode === 'proxy')
    .sort((a, b) => {
      const ra = Number(a.graph_revision ?? -1);
      const rb = Number(b.graph_revision ?? -1);
      if (rb !== ra) return rb - ra;
      return Number(b.timestamp || 0) - Number(a.timestamp || 0);
    });
  const preferred = matchingHash
    || matchingRev
    || byRev[0]
    || playable.find((r) => r.mode === 'proxy')
    || playable[0];
  if (!preferred?.id) return;
  const stale = Boolean(
    (currentHash && preferred.edit_graph_hash && preferred.edit_graph_hash !== currentHash)
    || (currentRev != null && preferred.graph_revision != null && preferred.graph_revision !== currentRev),
  );
  if (state.previewRenderId === preferred.id && player.src && !stale) return;

  // Keep the preference above, but fall through to older succeeded rows when
  // a durable job points at bytes that no longer exist in this project.
  const candidates = [preferred, ...playable].filter((render, index, all) => (
    render?.id && all.findIndex((item) => item.id === render.id) === index
  ));
  let latest = null;
  for (const candidate of candidates) {
    if (await _renderEndpointIsReachable(candidate)) {
      latest = candidate;
      break;
    }
  }
  if (!latest?.id) return;
  const latestStale = Boolean(
    (currentHash && latest.edit_graph_hash && latest.edit_graph_hash !== currentHash)
    || (currentRev != null && latest.graph_revision != null && latest.graph_revision !== currentRev),
  );
  if (latestStale) {
    showToast('Preview is outdated — rendering or click Render Proxy to update.', 'warn');
  }
  loadRenderInPreview(latest.id, latest.mode || 'proxy');
}

function loadRenderInPreview(renderId, mode = 'proxy') {
  if (!state.currentProjectId || !renderId) return;
  const player = $('#preview-player');
  const badge = $('#preview-mode-badge');
  const empty = $('#preview-empty');
  if (!player) return;
  state.previewRenderId = renderId;
  const url = api.renderFileUrl(state.currentProjectId, renderId);
  player.setAttribute('src', url);
  player.src = url;
  player.style.display = 'block';
  player.load();
  if (empty) {
    empty.classList.add('hidden');
    empty.style.display = 'none';
  }
  if (badge) {
    badge.textContent = mode === 'final'
      ? 'Final export · 1080p'
      : 'Review artifact · 640×360';
  }
  player.onerror = () => {
    showToast('Preview failed to load — click Render Proxy to rebuild.', 'error');
    if (empty) {
      empty.classList.remove('hidden');
      empty.style.display = '';
    }
  };
}

async function isProxyStale() {
  if (!state.currentProjectId) return false;
  const currentHash = state.currentProjectState?.edit_graph_hash;
  if (!currentHash) return false;
  try {
    const renders = await api.listRenders(state.currentProjectId);
    const latestProxy = renders.find(r => r.mode === 'proxy' && r.status === 'succeeded' && !(String(r.id||'').includes('.melt')));
    if (!latestProxy) return true;
    return latestProxy.edit_graph_hash && latestProxy.edit_graph_hash !== currentHash;
  } catch {
    return false;
  }
}

function updatePreviewTransport() {
  const player = $('#preview-player');
  const current = $('#tc-current');
  if (current) current.textContent = formatTimecode(state.playheadSec);

  const total = document.querySelector('.transport-total');
  const mediaDuration = Number(player?.duration);
  const duration = Number.isFinite(mediaDuration) && mediaDuration > 0
    ? mediaDuration
    : tlDurationSec;
  if (total) total.textContent = ` / ${duration > 0 ? formatTimecode(duration) : '—'}`;

  const play = $('#btn-play');
  if (play) {
    const playing = !!player && !player.paused && !player.ended;
    if (typeof play.replaceChildren === 'function') {
      play.replaceChildren(icon(playing ? 'pause' : 'play'));
    }
    play.title = playing ? 'Pause preview' : 'Play preview';
    play.setAttribute('aria-label', play.title);
  }
}

function updatePlayheadUi() {
  const label = $('#timeline-timecode-label');
  if (label) label.textContent = formatTimecode(state.playheadSec);
  const playhead = $('#timeline-playhead');
  if (playhead) playhead.style.left = `${secToPx(state.playheadSec)}px`;
  updatePreviewTransport();
}

function seekPreviewBy(delta) {
  const player = $('#preview-player');
  const mediaTime = Number(player?.currentTime);
  const current = Number.isFinite(mediaTime) ? mediaTime : (Number(state.playheadSec) || 0);
  const mediaDuration = Number(player?.duration);
  const duration = Number.isFinite(mediaDuration) && mediaDuration > 0
    ? mediaDuration
    : tlDurationSec;
  const target = duration > 0
    ? Math.max(0, Math.min(current + delta, duration))
    : Math.max(0, current + delta);
  state.playheadSec = target;
  if (player) {
    try { player.currentTime = target; } catch { /* ignore */ }
  }
  updatePlayheadUi();
}

function togglePreviewPlayback() {
  const player = $('#preview-player');
  if (!player) return;
  if (player.paused) {
    const pending = player.play();
    if (pending && typeof pending.catch === 'function') pending.catch(() => {});
  } else {
    player.pause();
  }
  updatePreviewTransport();
}

function seekToSec(sec) {
  const player = $('#preview-player');
  const mediaDuration = Number(player?.duration);
  const duration = tlDurationSec > 0
    ? tlDurationSec
    : (Number.isFinite(mediaDuration) && mediaDuration > 0 ? mediaDuration : 0);
  const clamped = Math.max(0, Math.min(Number(sec) || 0, duration));
  state.playheadSec = clamped;
  if (player && player.src) {
    try { player.currentTime = clamped; } catch { /* ignore */ }
  }
  updatePlayheadUi();
  const rulerCol = $('#timeline-ruler-col');
  if (rulerCol && tlDurationSec > 0) {
    const px = secToPx(clamped);
    const viewW = rulerCol.clientWidth;
    if (px < rulerCol.scrollLeft + 40 || px > rulerCol.scrollLeft + viewW - 40) {
      rulerCol.scrollLeft = Math.max(0, px - viewW / 2);
    }
  }
}

function timelineSecFromEvent(evt, container) {
  const rect = container.getBoundingClientRect();
  const x = evt.clientX - rect.left + (container.scrollLeft || 0);
  return x / (TL_BASE_PPS * tlZoom);
}

function fitTimelineToWindow() {
  const col = $('#timeline-ruler-col');
  if (!col || !tlDurationSec) return false;
  const availWidth = Math.max(col.clientWidth - 20, 100);
  // Long timelines (e.g. 30 min) need zoom << 0.05 to fit; the old 0.05
  // floor capped visible range at ~470s on a typical panel width.
  tlZoom = availWidth / (tlDurationSec * TL_BASE_PPS);
  tlZoom = Math.max(0.001, Math.min(tlZoom, 8));
  return true;
}

let tlScrubbing = false;
let tlAutoFitPending = false;

function bindTimelineScrubbing() {
  const rulerCol = $('#timeline-ruler-col');
  if (!rulerCol || rulerCol.dataset.scrubBound === '1') return;
  rulerCol.dataset.scrubBound = '1';
  rulerCol.addEventListener('mousedown', (evt) => {
    if (evt.button !== 0) return;
    if (evt.target.closest('.timeline-edit-marker, .timeline-note-marker')) return;
    tlScrubbing = true;
    seekToSec(timelineSecFromEvent(evt, rulerCol));
    evt.preventDefault();
  });
  document.addEventListener('mousemove', (evt) => {
    if (!tlScrubbing) return;
    const col = $('#timeline-ruler-col');
    if (!col) return;
    seekToSec(timelineSecFromEvent(evt, col));
  });
  document.addEventListener('mouseup', () => { tlScrubbing = false; });
}

function opPositionSec(edit) {
  const p = edit?.payload || {};
  if (typeof p.position_sec === 'number') return p.position_sec;
  return null;
}

async function copyPlayheadTimecode() {
  const text = `[${formatTimecode(state.playheadSec)}]`;
  try {
    await navigator.clipboard.writeText(text);
    showToast(`Copied ${text}`, 'success');
  } catch {
    showToast(text, 'info');
  }
}

async function addNoteAtPlayhead() {
  if (!state.currentProjectId) return;
  const text = prompt('Note for the agent at this time:', '');
  if (!text || !text.trim()) return;
  try {
    await api.createNote(state.currentProjectId, {
      text: text.trim(),
      t_start: state.playheadSec,
      t_end: state.playheadSec,
    });
    showToast('Note added at playhead', 'success');
    await loadProjectState();
  } catch (err) {
    showToast(`Note failed: ${err.message}`, 'error');
  }
}

// ============================================================
// Timeline Panel (added: HTML Overlay support)
// ============================================================

/** Pixels per second at zoom=1 */
const TL_BASE_PPS = 60;
let tlZoom = 1.0;
let tlDurationSec = 0;
let tlCurrentData = null;
let tlEditMarkers = [];
let tlNoteMarkers = [];

/** Convert seconds to pixels using current zoom level */
function secToPx(sec) { return sec * TL_BASE_PPS * tlZoom; }

/** Draw the seconds ruler */
function renderRuler(durationSec) {
  const ruler = $('#timeline-ruler');
  if (!ruler) return;
  ruler.innerHTML = '';
  const step = tlZoom < 0.02 ? 60 : tlZoom < 0.05 ? 30 : tlZoom < 0.5 ? 10 : tlZoom < 1.5 ? 5 : 2;
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
export function renderTimeline(timelineData, context = {}) {
  tlCurrentData = timelineData;
  tlEditMarkers = context.edits || [];
  tlNoteMarkers = context.notes || [];
  const labelsCol = $('#timeline-track-labels');
  const tracksArea = $('#timeline-tracks-area');
  const emptyMsg = $('#timeline-empty-msg');
  const durationLabel = $('#timeline-duration-label');
  const rulerCol = $('#timeline-ruler-col');
  if (!labelsCol || !tracksArea) return;

  const tracks = timelineData?.tracks ?? [];
  const overlays = timelineData?.overlays ?? [];
  const remotions = timelineData?.remotion_compositions ?? [];
  const durationSec = timelineData?.duration_sec ?? 0;
  tlDurationSec = durationSec;

  if (durationLabel) {
    durationLabel.textContent = durationSec > 0
      ? `${durationSec.toFixed(1)}s`
      : '—';
  }
  updatePlayheadUi();

  // Clear previous content (keep the ruler header placeholder in labels)
  labelsCol.innerHTML = '<div class="timeline-track-label-row" style="height:20px;border-bottom:1px solid var(--border);"></div>';
  tracksArea.innerHTML = '';

  const onSeekClick = (evt) => {
    if (evt.target.closest('.timeline-edit-marker, .timeline-note-marker')) return;
    const col = $('#timeline-ruler-col');
    const sec = timelineSecFromEvent(evt, col || evt.currentTarget);
    seekToSec(sec);
  };

  if (tracks.length === 0) {
    if (emptyMsg) tracksArea.appendChild(emptyMsg);
    emptyMsg && (emptyMsg.style.display = '');
    renderRuler(10);
    const ruler = $('#timeline-ruler');
    ruler?.addEventListener('click', onSeekClick);
    tracksArea.addEventListener('click', onSeekClick);
    return;
  }
  if (emptyMsg) emptyMsg.style.display = 'none';

  renderRuler(Math.max(durationSec, 10));
  const ruler = $('#timeline-ruler');
  ruler?.addEventListener('click', onSeekClick);
  tracksArea.addEventListener('click', onSeekClick);

  // Calculate total overlay height (one row per overlay track in the future;
  // for now, overlay markers live on top of all tracks)
  const totalWidth = secToPx(Math.max(durationSec, 10));
  tracksArea.style.width = `${totalWidth}px`;

  tracks.forEach((track) => {
    // Label
    const kindBadge = el('span', {
      class: `track-kind-badge ${track.kind ?? 'video'}`,
    }, [icon(track.kind === 'audio' ? 'audio' : 'video')]);
    const labelRow = el('div', { class: 'timeline-track-label-row' }, [
      kindBadge,
      document.createTextNode(track.track_id ?? ''),
    ]);
    labelsCol.appendChild(labelRow);

    // Track row
    const trackRow = el('div', { class: 'timeline-track-row', style: `width:${totalWidth}px` });

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
        title: `${clip.clip_id ?? ''}\n${clip.asset_hash ?? ''}\n${clip.position_sec?.toFixed(2)}s -> ${(clip.position_sec + clipDur).toFixed(2)}s`,
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

    // Remotion composition markers (pending until asset_hash is set)
    remotions.forEach((rc) => {
      if (rc.track_id && track.track_id && rc.track_id !== track.track_id) return;
      const left = secToPx(rc.position_sec ?? 0);
      const width = Math.max(secToPx(rc.duration_sec ?? 0), 4);
      const pending = !rc.asset_hash;
      const marker = el('div', {
        class: 'timeline-remotion-marker' + (pending ? ' pending' : ''),
        style: `left:${left}px;width:${width}px`,
        title: pending
          ? `Remotion (pending materialize): ${rc.composition_id ?? ''}`
          : `Remotion: ${rc.composition_id ?? ''}\n${rc.asset_hash ?? ''}`,
      });
      trackRow.appendChild(marker);
    });

    tracksArea.appendChild(trackRow);
  });

  // Edit op markers (first track row only)
  const markerRow = tracksArea.querySelector('.timeline-track-row');
  if (markerRow) {
    for (const edit of tlEditMarkers) {
      const pos = opPositionSec(edit);
      if (pos == null) continue;
      const marker = el('div', {
        class: 'timeline-edit-marker' + (edit.status === 'reverted' ? ' reverted' : ''),
        style: `left:${secToPx(pos)}px`,
        title: `${edit.kind} @ ${formatTimecode(pos)}\n${edit.summary || ''}`,
      });
      marker.addEventListener('click', (evt) => {
        evt.stopPropagation();
        selectEdit(edit);
        seekToSec(pos);
        const editsTab = document.querySelector('.panel-tabs .tab[data-tab="edits"]');
        editsTab?.click();
      });
      markerRow.appendChild(marker);
    }
    for (const note of tlNoteMarkers) {
      if (note.status && note.status !== 'pending') continue;
      const pos = Number(note.timestamp) || 0;
      const marker = el('div', {
        class: 'timeline-note-marker',
        style: `left:${secToPx(pos)}px`,
        title: `Note @ ${formatTimecode(pos)}: ${note.text || ''}`,
      });
      marker.addEventListener('click', (evt) => {
        evt.stopPropagation();
        seekToSec(pos);
        openNotesModal();
      });
      markerRow.appendChild(marker);
    }
  }

  if (rulerCol) {
    rulerCol.onclick = (evt) => {
      if (evt.target.closest('.timeline-edit-marker, .timeline-note-marker')) return;
      onSeekClick(evt);
    };
  }

  bindTimelineScrubbing();

  if (durationSec > 120 && !tlAutoFitPending) {
    tlAutoFitPending = true;
    fitTimelineToWindow();
    renderTimeline(timelineData, context);
    return;
  }
}

// ---- Zoom controls ----
$('#btn-timeline-zoom-in')?.addEventListener('click', () => {
  tlZoom = Math.min(tlZoom * 1.5, 8);
  if (tlCurrentData) renderTimeline(tlCurrentData, { edits: tlEditMarkers, notes: tlNoteMarkers });
});
$('#btn-timeline-zoom-out')?.addEventListener('click', () => {
  tlZoom = Math.max(tlZoom / 1.5, 0.001);
  if (tlCurrentData) renderTimeline(tlCurrentData, { edits: tlEditMarkers, notes: tlNoteMarkers });
});
$('#btn-timeline-fit')?.addEventListener('click', () => {
  if (fitTimelineToWindow() && tlCurrentData) {
    renderTimeline(tlCurrentData, { edits: tlEditMarkers, notes: tlNoteMarkers });
  }
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
  if (tl) {
    renderTimeline(tl, {
      edits: normalizeEdits(rawState),
      notes: normalizeNotes(rawState).list,
    });
  }
}
