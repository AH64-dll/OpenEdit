/* Optional graphics studio: source writer → durable preview → revision-checked IR. */
import { state } from './state.js';

const el = id => document.getElementById(`graphics-${id}`);
const panel = el('panel'), source = el('source'), canvas = el('canvas'), video = el('video');
const form = el('properties'), select = el('element');
const drafts = new Map();
let shown = null, loading = false, drag = null;
const current = () => drafts.get(state.currentProjectId);
const endpoint = (id, suffix = '') => `/api/projects/${encodeURIComponent(id)}${suffix}`;
const message = text => { el('status').textContent = text; };
async function request(id, suffix, body) {
  const response = await fetch(endpoint(id, suffix), body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) { const error = new Error(data.error || data.detail || 'Graphics request failed'); error.stale = response.status === 409; throw error; }
  return data;
}
function controls() {
  const d = current(), busy = !d || d.busy;
  source.disabled = busy;
  el('preview').disabled = busy || d?.stale || !d?.worker_ready;
  el('cancel').disabled = !d?.job || !d?.busy;
  el('commit').disabled = busy || d?.stale || !d?.accepted || d.acceptedSource !== d.source ||
    d.acceptedDuration !== Number(el('duration').value) || d.acceptedFps !== Number(el('fps').value);
  el('reload').disabled = busy || loading;
  const item = layer();
  for (const input of form.elements) {
    const derivedSize = item?.tag === 'group' && ['width', 'height'].includes(input.name);
    const animated = d?.elements?.some(e => e.tag === 'keyframeTrack' && e.parent_id === item?.id && e.property === input.name);
    input.disabled = busy || d?.stale || !select.value || derivedSize || animated;
    input.title = derivedSize ? 'Group size comes from its children.' : animated ? 'Edit this animated property in the JSX keyframes.' : '';
  }
  el('commit').textContent = d?.existing ? 'Update timeline clip' : 'Add to timeline';
}
function remember() {
  const d = current(); if (!d) return;
  try { sessionStorage.setItem(`open_edit.graphics.${state.currentProjectId}`, JSON.stringify({
    source: d.source, graph_revision: d.graph_revision, clip_id: el('clip-id').value,
    duration: el('duration').value, fps: el('fps').value,
  })); } catch {}
}
function layer() { return current()?.elements?.find(e => e.id === select.value); }
function outline() {
  const ctx = canvas.getContext('2d'); ctx.clearRect(0, 0, canvas.width, canvas.height);
  const item = layer(); if (!item || item.parent_id !== current()?.scene?.id) return;
  const d = drag || item;
  ctx.strokeStyle = '#55b5ff'; ctx.lineWidth = 2 * canvas.width / Math.max(canvas.clientWidth, 1);
  ctx.strokeRect(d.x || 0, d.y || 0, item.width || 100, item.height || 60);
}
function selectLayer() {
  const item = layer();
  if (item) for (const key of ['x', 'y', 'width', 'height']) form.elements[key].value = item[key] ?? (['width', 'height'].includes(key) ? 100 : 0);
  outline(); controls();
}
function paint() {
  const d = current(), selected = select.value;
  source.value = d?.source || ''; select.replaceChildren();
  for (const item of d?.elements || []) {
    if (!['rect', 'text', 'image', 'group'].includes(item.tag) || item.clipPath) continue;
    const option = document.createElement('option'); option.value = item.id; option.textContent = `${item.tag} · ${item.id}`; select.append(option);
  }
  if ([...select.options].some(o => o.value === selected)) select.value = selected;
  if (d?.scene) { canvas.width = d.scene.width; canvas.height = d.scene.height; canvas.parentElement.style.aspectRatio = `${d.scene.width}/${d.scene.height}`; }
  selectLayer();
}
async function load(discard = false) {
  const id = state.currentProjectId; if (!id || loading) return;
  loading = true; controls();
  try {
    const clip = el('clip-id').value || 'graphics';
    const view = await request(id, `/graphics?clip_id=${encodeURIComponent(clip)}`);
    let d = drafts.get(id);
    if (d && !discard) {
      if (d.graph_revision === view.graph_revision) return;
      d.stale = true;
    }
    else {
      d = { ...view, busy: false, stale: false, elements: [] };
      if (!discard) try {
        const saved = JSON.parse(sessionStorage.getItem(`open_edit.graphics.${id}`));
        if (typeof saved?.source === 'string' && Number.isInteger(saved.graph_revision)) {
          d.source = saved.source; d.stale = saved.graph_revision !== view.graph_revision;
          d.graph_revision = saved.graph_revision;
          el('duration').value = saved.duration || 3; el('fps').value = saved.fps || 30;
        }
      } catch {}
      drafts.set(id, d);
      if (view.worker_ready && !d.stale) {
        const inspected = await request(id, '/graphics/source', { source: d.source, edits: [], expected_revision: d.graph_revision });
        Object.assign(d, inspected);
      }
    }
    if (id !== state.currentProjectId) return;
    shown = id;
    if (d.last_good_job_id && !video.getAttribute('src')) {
      video.src = endpoint(id, `/graphics/${d.last_good_job_id}/preview`);
      video.poster = endpoint(id, `/graphics/${d.last_good_job_id}/poster`);
      video.load();
    }
    paint(); message(d.stale ? 'Project changed. Your graphics draft is kept; copy it before reloading.' :
      d.worker_ready ? `Revision ${d.graph_revision} · render a preview, then add it to the timeline.` : 'Install the optional graphics worker to render this source.');
  } catch (error) { if (id === state.currentProjectId) message(error.message); }
  finally { loading = false; controls(); }
}
async function rewrite(props) {
  const d = current(), id = state.currentProjectId; if (!d || d.busy || d.stale || !select.value) return;
  d.busy = true; controls();
  try {
    const result = await request(id, '/graphics/source', { source: d.source, expected_revision: d.graph_revision,
      edits: [{ kind: 'set', source: `index.tsx:${select.value}`, props }],
    });
    Object.assign(d, result); d.accepted = null;
    if (id === state.currentProjectId) { paint(); remember(); message('Layer updated in JSX. Render a new preview to apply it.'); }
  } catch (error) { d.stale = !!error.stale; if (id === state.currentProjectId) message(error.message); }
  finally { d.busy = false; controls(); }
}
async function preview() {
  const d = current(), id = state.currentProjectId; if (!d || d.busy || d.stale) return;
  d.busy = true; const submitted = d.source;
  const duration = Number(el('duration').value), fps = Number(el('fps').value);
  controls(); message('Rendering graphics…');
  try {
    const queued = await request(id, '/render', { mode: 'graphics', expected_revision: d.graph_revision,
      graphics: { source: submitted, duration_sec: duration, fps },
    });
    d.job = queued.job_id; controls();
    let job;
    do {
      await new Promise(r => setTimeout(r, 750));
      job = await request(id, `/render_jobs/${queued.job_id}`);
    } while (['queued', 'running', 'cancelling'].includes(job.status));
    if (job.status !== 'succeeded') throw new Error(job.error || `Preview ${job.status}. Last good preview kept.`);
    d.accepted = queued.job_id; d.acceptedSource = submitted; d.acceptedDuration = duration; d.acceptedFps = fps;
    Object.assign(d, { elements: job.result.elements, scene: job.result.scene });
    if (id === state.currentProjectId) {
      video.src = endpoint(id, `/graphics/${queued.job_id}/preview`);
      video.poster = endpoint(id, `/graphics/${queued.job_id}/poster`);
      video.load(); paint(); message('Preview passed quality checks. Select a layer or drag it; add when ready.');
    }
  } catch (error) { d.stale = !!error.stale; if (id === state.currentProjectId) message(error.message); }
  finally { d.busy = false; d.job = null; controls(); }
}
source.addEventListener('input', () => { const d = current(); if (!d) return; d.source = source.value; remember(); controls(); message('Unsaved graphics draft · render to check changes.'); });
select.addEventListener('change', selectLayer);
form.addEventListener('submit', event => { event.preventDefault(); rewrite(Object.fromEntries(['x', 'y', 'width', 'height'].filter(k => !form.elements[k].disabled).map(k => [k, Number(form.elements[k].value)]))); });
el('preview').addEventListener('click', preview);
el('reload').addEventListener('click', () => load(true));
el('cancel').addEventListener('click', async () => {
  const id = state.currentProjectId, d = current(); if (d?.job) try { await request(id, `/render_jobs/${d.job}/cancel`, {}); } catch (error) { message(error.message); }
});
el('commit').addEventListener('click', async () => {
  const d = current(), id = state.currentProjectId; if (!d || el('commit').disabled) return;
  d.busy = true; controls();
  try {
    const result = await request(id, '/graphics/commit', { job_id: d.accepted, expected_revision: d.graph_revision, clip_id: el('clip-id').value || 'graphics' });
    d.graph_revision = result.graph_revision; d.existing = true; d.accepted = null;
    if (id === state.currentProjectId) {
      remember(); message(`Graphics saved · revision ${result.graph_revision}`);
      window.dispatchEvent(new CustomEvent('openedit:graph-changed', { detail: { projectId: id } }));
    }
  } catch (error) { d.stale = !!error.stale; if (id === state.currentProjectId) message(d.stale ? 'Project changed. Your graphics draft is kept; reload before applying.' : error.message); }
  finally { d.busy = false; controls(); }
});
el('play').addEventListener('click', () => { if (video.paused) video.play().catch(() => {}); else video.pause(); });
for (const id of ['duration', 'fps']) el(id).addEventListener('input', () => { remember(); controls(); });
canvas.addEventListener('pointerdown', event => {
  const d = current(); if (!d || d.busy || d.stale) return;
  const rect = canvas.getBoundingClientRect(), x = (event.clientX - rect.left) * canvas.width / rect.width, y = (event.clientY - rect.top) * canvas.height / rect.height;
  const item = [...(d.elements || [])].reverse().find(e => e.parent_id === d.scene?.id && ['rect', 'text', 'image', 'group'].includes(e.tag) && !e.clipPath &&
    x >= (e.x || 0) && y >= (e.y || 0) && x <= (e.x || 0) + (e.width || 100) && y <= (e.y || 0) + (e.height || 60));
  if (!item) return;
  video.pause(); video.currentTime = 0; select.value = item.id; selectLayer();
  if (form.elements.x.disabled || form.elements.y.disabled) { message('Edit animated position in the JSX keyframes.'); return; }
  drag = { x: item.x || 0, y: item.y || 0, startX: x, startY: y, originX: item.x || 0, originY: item.y || 0 };
  canvas.setPointerCapture(event.pointerId);
});
canvas.addEventListener('pointermove', event => {
  if (!drag) return; const rect = canvas.getBoundingClientRect();
  drag.x = Math.round(drag.originX + (event.clientX - rect.left) * canvas.width / rect.width - drag.startX);
  drag.y = Math.round(drag.originY + (event.clientY - rect.top) * canvas.height / rect.height - drag.startY); outline();
});
canvas.addEventListener('pointerup', () => { if (!drag) return; const props = { x: drag.x, y: drag.y }; drag = null; rewrite(props); });
canvas.addEventListener('pointercancel', () => { drag = null; outline(); });
panel.addEventListener('toggle', () => { if (panel.open) load(); });
setInterval(() => {
  if (!panel.open || loading || current()?.busy) return;
  if (shown !== state.currentProjectId) { shown = state.currentProjectId; video.removeAttribute('src'); video.removeAttribute('poster'); video.load(); paint(); }
  load();
}, 5000);
controls();
