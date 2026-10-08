/* Optional JSX editor. Every code and property write uses the same IR adapter. */
import { state } from './state.js';

const panel = document.getElementById('authoring-panel');
const source = document.getElementById('authoring-source');
const status = document.getElementById('authoring-status');
const apply = document.getElementById('authoring-apply');
const reload = document.getElementById('authoring-reload');
const form = document.getElementById('authoring-properties');
const clips = document.getElementById('authoring-clip');
const applyClip = document.getElementById('authoring-apply-properties');
const drafts = new Map();
let shownProject = null;
let fetching = false;

function current() { return drafts.get(state.currentProjectId); }
function dirty(d) { return d && d.source !== d.baseline; }
function message(text) { status.textContent = text; }
function controls() {
  const d = current();
  source.disabled = !d || d.busy;
  apply.disabled = !d || d.busy || d.stale || !d.worker_ready;
  applyClip.disabled = apply.disabled || dirty(d) || !clips.value;
  reload.disabled = !!d?.busy || fetching || !state.currentProjectId;
  for (const input of form.querySelectorAll('input, select')) input.disabled = applyClip.disabled;
  // Selection remains available even while the source has an unsaved draft.
  clips.disabled = !d || d.busy || !d.elements?.length;
}
function selectClip() {
  const item = current()?.elements?.find(c => c.source_id === clips.value);
  if (item) for (const key of ['start', 'sourceIn', 'sourceOut', 'volume', 'playbackRate']) {
    form.elements[key].value = item[key];
  }
  controls();
}
function paint() {
  const d = current();
  const focused = document.activeElement === source;
  const selection = [source.selectionStart, source.selectionEnd];
  const selectedClip = clips.value;
  source.value = d?.source || '';
  clips.replaceChildren();
  for (const clip of d?.elements || []) {
    const option = document.createElement('option');
    option.value = clip.source_id;
    option.textContent = `${clip.tag} · ${decodeURIComponent(clip.id.slice(2))}`;
    clips.append(option);
  }
  if ([...clips.options].some(option => option.value === selectedClip)) clips.value = selectedClip;
  if (focused) source.setSelectionRange(...selection);
  selectClip();
  controls();
}
function remember() {
  const d = current();
  if (!d) return;
  try {
    const key = `open_edit.jsx_draft.${state.currentProjectId}`;
    if (dirty(d)) sessionStorage.setItem(key, JSON.stringify({ source: d.source, revision: d.graph_revision }));
    else sessionStorage.removeItem(key);
  } catch { /* Editing still works when browser storage is unavailable. */ }
}
async function request(id, body) {
  const response = await fetch(`/api/projects/${encodeURIComponent(id)}/authoring${body ? '' : '?include_source=true'}`, body ? {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  } : {});
  const result = await response.json();
  if (!response.ok) {
    const error = new Error(result.error || result.detail || 'Authoring request failed');
    error.stale = response.status === 409;
    throw error;
  }
  return result;
}
async function load(discard = false) {
  const id = state.currentProjectId;
  if (!id || fetching) return;
  fetching = true;
  controls();
  try {
    const view = await request(id);
    const previous = drafts.get(id);
    let d = { ...view, baseline: view.source, stale: false, busy: false };
    if (!discard && dirty(previous)) {
      d = { ...previous, stale: previous.graph_revision !== view.graph_revision };
    } else if (!discard && !previous) {
      try {
        const saved = JSON.parse(sessionStorage.getItem(`open_edit.jsx_draft.${id}`));
        if (typeof saved?.source === 'string' && Number.isInteger(saved.revision)) {
          d.source = saved.source;
          d.graph_revision = saved.revision;
          d.stale = saved.revision !== view.graph_revision;
        }
      } catch { /* A malformed browser draft does not replace graph data. */ }
    }
    drafts.set(id, d);
    if (state.currentProjectId !== id) return;
    paint();
    remember();
    message(d.stale ? 'Project changed. Your draft is kept; copy it before reloading source.' :
      !d.worker_ready ? 'Source available. Install the optional Diffusion worker to apply edits.' :
      dirty(d) ? `Unsaved draft · revision ${d.graph_revision}` :
      `Revision ${d.graph_revision}${d.elements_truncated ? ' · first 50 clips shown' : ''}`);
  } catch (error) {
    if (state.currentProjectId === id) message(error.message);
  } finally { fetching = false; controls(); }
}
async function save(body) {
  const id = state.currentProjectId;
  const d = current();
  if (!d || d.busy || d.stale) return;
  d.busy = true;
  controls();
  message('Applying edit…');
  try {
    const result = await request(id, { expected_revision: d.graph_revision, ...body });
    // Mark the submitted draft clean before loading the accepted source.
    d.baseline = d.source;
    d.busy = false;
    try { sessionStorage.removeItem(`open_edit.jsx_draft.${id}`); } catch {}
    if (state.currentProjectId === id) {
      remember();
      await load(true);
      message(`Saved · revision ${result.graph_revision}`);
      window.dispatchEvent(new CustomEvent('openedit:graph-changed', { detail: { projectId: id } }));
    } else drafts.delete(id);
  } catch (error) {
    d.stale = !!error.stale;
    if (state.currentProjectId === id) message(d.stale ?
      'Project changed. Your draft is kept; copy it before reloading source.' : error.message);
  } finally { d.busy = false; controls(); }
}
source.addEventListener('input', () => {
  const d = current();
  if (!d) return;
  d.source = source.value;
  remember();
  controls();
  message(d.stale ? 'Project changed. Your draft is kept; copy it before reloading source.' :
    `Unsaved draft · revision ${d.graph_revision}`);
});
clips.addEventListener('change', selectClip);
reload.addEventListener('click', () => load(true));
apply.addEventListener('click', () => save({ source: current()?.source }));
form.addEventListener('submit', event => {
  event.preventDefault();
  if (applyClip.disabled) return;
  const props = Object.fromEntries(['start', 'sourceIn', 'sourceOut', 'volume', 'playbackRate'].map(key => [key, Number(form.elements[key].value)]));
  save({ edits: [{ kind: 'set', source: clips.value, props }] });
});
panel.addEventListener('toggle', () => { if (panel.open) load(); });
document.getElementById('project-select').addEventListener('change', () => {
  shownProject = state.currentProjectId;
  paint();
  if (panel.open) load();
});
setInterval(() => {
  if (!panel.open || fetching || current()?.busy) return;
  if (shownProject !== state.currentProjectId) { shownProject = state.currentProjectId; paint(); }
  if (state.currentProjectId) load();
}, 5000);
controls();
