/* Source-backed graphics, shared selection and separate non-rendered AI marks. */
import { state } from './state.js';
import { studio, loadStudio, studioRequest, commitStudio, studioObject, selectObjects, selectMarks } from './studio-state.js';
import { inverse, transformPoint, localDelta, insidePolygon, bounds, selectionRoots, layerLocked, annotationPoints, alignmentOffsets } from './studio-geometry.js';
import { keyframeEdits } from './keyframes.js';
import { convertMark } from './media-marks.js';

const el = id => document.getElementById(`graphics-${id}`);
const panel = el('panel'), source = el('source'), canvas = el('canvas'), live = el('live');
const form = el('properties'), select = el('element'), guides = el('guides');
let draft, renderer, geometry = [], drag, playing = false, time = 0, generation = 0, runtimeReady;
let busy = false, checkedJob = null, checkedSource = null, lastProject = null, loadingSnapshot = false, saving = false;
let pendingSnapshot = false, pendingDiscard = false, snapshotTask = null, playGeneration = 0;
const message = text => { el('status').textContent = text; };
const uid = prefix => `${prefix}-${crypto.randomUUID()}`;
const visual = e => ['rect', 'text', 'image', 'group'].includes(e.tag) && !e.clipPath;
const elements = () => draft?.data.elements || [];
const item = () => elements().find(e => e.id === studio.selectedIds[0]);
const dirty = () => draft && source.value !== draft.data.source;
const previewKey = data => JSON.stringify([state.currentProjectId, data.source, data.fps, data.duration_sec]);
function invalidateChecked(data) { if (checkedSource !== previewKey(data)) { el('checked').checked = false; el('video').hidden = true; } }
const locked = id => layerLocked(id, elements(), draft?.data.locked_ids || [], draft?.data.locked);
const roots = () => selectionRoots(studio.selectedIds, elements());
const mark = () => studioObject('annotation', studio.selectedMarks[0]);
const fail = error => message(error.stale ? 'Project changed. Your source draft is kept; reload before applying it.' : error.message);
const safe = fn => async (...args) => { try { await fn(...args); } catch (error) { fail(error); } };

function controls() {
  const disabled = !draft || busy || studio.busy || saving || loadingSnapshot, selection = item(), selectedLocked = studio.selectedIds.some(locked);
  source.disabled = disabled || draft?.data.locked;
  el('commit').disabled = disabled || draft?.stale || draft?.data.locked;
  el('commit').textContent = draft?.saved ? 'Save source' : 'Add to timeline';
  el('preview').disabled = disabled || draft?.stale;
  el('cancel').disabled = !checkedJob; el('reload').disabled = busy || studio.busy;
  el('new').disabled = busy || studio.busy || !state.currentProjectId;
  el('checked').disabled = !el('video').getAttribute('src');
  for (const input of form.elements) {
    input.disabled = disabled || dirty() || !selection || selectedLocked;
    if (['width', 'height'].includes(input.name) && selection?.tag === 'group') input.disabled = true;
    if (['fontSize', 'text'].includes(input.name) && selection?.tag !== 'text') input.disabled = true;
    if (input.name === 'color' && !['text', 'rect'].includes(selection?.tag)) input.disabled = true;
  }
  for (const id of ['group', 'duplicate', 'delete', 'forward', 'backward', 'align']) el(id).disabled = disabled || dirty() || !selection || selectedLocked;
  el('hidden').disabled = disabled || !selection || selectedLocked || dirty();
  el('locked').disabled = disabled || !selection || draft?.data.locked || dirty();
  el('selection-status').textContent = studio.selectedIds.length ? `${studio.selectedIds.length} selected${selectedLocked ? ' · locked' : ''}` : 'Select an object or drag a selection box.';
}
function inspector() {
  const selected = item(); select.value = selected?.id || '';
  if (selected) {
    const defaults = { x: 0, y: 0, width: 100, height: 60, rotation: 0, scale: 1, opacity: 1, color: '#ffffff', fontSize: 48, text: '' };
    const values = studio.autoKey ? {...selected,...geometry.find(g=>g.id===selected.id)} : selected;
    for (const [key, fallback] of Object.entries(defaults)) form.elements[key].value = values[key] ?? (key === 'color' ? selected.fill : undefined) ?? fallback;
    el('hidden').checked = !!selected.hidden; el('locked').checked = locked(selected.id);
  }
  const current = mark(), f = el('mark-properties'); f.hidden = !current;
  if (current) for (const name of ['text', 'scope', 'anchor_sec', 'end_sec']) f.elements[name].value = current.data[name] ?? '';
  controls();
}
function layerLists() {
  const list = el('layers'); list.replaceChildren(); select.replaceChildren();
  for (const layer of elements().filter(visual)) {
    const option = document.createElement('option'); option.value = layer.id; option.textContent = `${layer.tag} · ${layer.id}`; select.append(option);
    const row = document.createElement('button'); row.type = 'button'; row.className = 'studio-layer';
    row.classList.toggle('selected', studio.selectedIds.includes(layer.id)); row.dataset.objectId = layer.id;
    let depth = 0, parent = layer.parent_id;
    while (parent && elements().find(e => e.id === parent)?.tag !== 'scene') { depth++; parent = elements().find(e => e.id === parent)?.parent_id; }
    row.style.paddingLeft = `${12 + depth * 14}px`;
    row.textContent = `${locked(layer.id) ? '🔒 ' : layer.hidden ? '◌ ' : ''}${layer.tag === 'text' ? (layer.text || layer.id).slice(0, 36) : layer.id}`;
    row.title = `${layer.tag} · ${layer.id}`;
    row.addEventListener('click', event => { selectMarks([]); selectObjects(event.shiftKey ? [...new Set([...studio.selectedIds, layer.id])] : [layer.id], draft.object_id); });
    list.append(row);
  }
  const marks = el('marks'); marks.replaceChildren();
  for (const obj of studio.objects.filter(o => o.kind === 'annotation' && (!o.data.document_id || o.data.document_id === draft?.object_id))) {
    const row = document.createElement('button'); row.type = 'button'; row.className = 'studio-layer';
    row.classList.toggle('selected', studio.selectedMarks.includes(obj.object_id)); row.textContent = `${obj.data.tool} · ${obj.data.text || obj.object_id}`;
    row.addEventListener('click', safe(async () => { selectMarks([obj.object_id]); await seek(Math.max(0, obj.data.anchor_sec - (draft?.data.position_sec || 0))); })); marks.append(row);
  }
  inspector();
}
const svg = (tag, attrs = {}) => {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value)); return node;
};
function drawMark(mark, points, stroke, selected) {
  if (!points.length) return;
  const attrs = { fill: 'none', stroke: mark.color, 'stroke-width': stroke * (selected ? 1.5 : 1), 'stroke-linecap': 'round' }, [a, b = a] = points;
  if (mark.tool === 'rectangle') { const box = bounds(points); guides.append(svg('rect', { ...attrs, x: box.left, y: box.top, width: box.right - box.left, height: box.bottom - box.top })); }
  else if (mark.tool === 'arrow') {
    guides.append(svg('line', { ...attrs, x1: a[0], y1: a[1], x2: b[0], y2: b[1] }));
    const angle = Math.atan2(b[1] - a[1], b[0] - a[0]), size = stroke * 7;
    const tips = [b, [b[0] - size * Math.cos(angle - .5), b[1] - size * Math.sin(angle - .5)], [b[0] - size * Math.cos(angle + .5), b[1] - size * Math.sin(angle + .5)]];
    guides.append(svg('polygon', { points: tips.map(p => p.join(',')).join(' '), fill: mark.color }));
  } else if (mark.tool === 'freehand') guides.append(svg('polyline', { ...attrs, points: points.map(p => p.join(',')).join(' ') }));
  else guides.append(svg('circle', { ...attrs, cx: a[0], cy: a[1], r: stroke * 4 }));
  if (mark.text) { const text = svg('text', { x: a[0] + stroke * 5, y: a[1] - stroke * 4, fill: mark.color, 'font-size': stroke * 9 }); text.textContent = mark.text; guides.append(text); }
}
function drawGuides() {
  guides.replaceChildren(); const stroke = 2 * canvas.width / Math.max(canvas.clientWidth, 1);
  for (const g of geometry.filter(g => studio.selectedIds.includes(g.id) && g.visible)) guides.append(svg('polygon', { points: g.corners.map(p => p.join(',')).join(' '), fill: 'none', stroke: '#73beff', 'stroke-width': stroke }));
  const globalTime = time + (draft?.data.position_sec || 0);
  for (const obj of studio.objects.filter(o => o.kind === 'annotation' && !o.data.hidden && (!o.data.document_id || o.data.document_id === draft?.object_id) &&
    (o.data.scope === 'object' || (o.data.scope === 'frame' ? Math.abs(o.data.anchor_sec - globalTime) < 1 / (draft?.data.fps || 30) : globalTime >= o.data.anchor_sec && globalTime <= o.data.end_sec)))) {
    drawMark(obj.data, annotationPoints(obj.data, geometry), stroke, studio.selectedMarks.includes(obj.object_id));
  }
  if (drag?.mode === 'mark') drawMark({ tool: drag.tool, color: '#ffcc55', text: '' }, drag.points, stroke, true);
  if (drag?.mode === 'box') { const box = bounds([drag.start, drag.end]); guides.append(svg('rect', { x: box.left, y: box.top, width: box.right - box.left, height: box.bottom - box.top, fill: '#55b5ff22', stroke: '#73beff', 'stroke-width': stroke })); }
}
async function runtime() {
  if (window.OpenEditCanvas) return;
  if (!runtimeReady) runtimeReady = new Promise((resolve, reject) => {
    const script = document.createElement('script'); script.src = '/api/studio/runtime.js'; script.onload = resolve;
    script.onerror = () => { runtimeReady = null; script.remove(); reject(new Error('Open Setup to install the graphics compiler.')); }; document.head.append(script);
  }); await runtimeReady;
}
async function mountDraft() {
  if (!draft || !panel.open) return;
  const token = ++generation, project = state.currentProjectId, captured = draft;
  const config = await studioRequest('/studio/compile', { expected_revision: studio.revision, source: captured.data.source }); await runtime();
  if (token !== generation || project !== state.currentProjectId) return;
  await renderer?.dispose(); renderer = null;
  const next = await window.OpenEditCanvas.create(live, { code: config.code, fps: captured.data.fps, assets: config.asset_manifest });
  if (token !== generation || project !== state.currentProjectId) { await next.dispose(); return; }
  renderer = next; Object.assign(captured.data, { elements: config.elements, scene: config.scene });
  invalidateChecked(captured.data);
  canvas.width = config.scene.width; canvas.height = config.scene.height; guides.setAttribute('viewBox', `0 0 ${canvas.width} ${canvas.height}`);
  canvas.parentElement.style.aspectRatio = `${canvas.width}/${canvas.height}`;
  layerLists(); await seek(time); message(`Interactive canvas · ${captured.saved ? 'saved source' : 'new composition'} · revision ${studio.revision}`);
}
async function seek(value, offsets = {}) {
  time = Math.max(0, Math.min(Number(value) || 0, draft?.data.duration_sec || 3));
  el('seek').value = time; el('time').textContent = `${time.toFixed(2)} s`; state.playheadSec = time + (draft?.data.position_sec || 0);
  window.dispatchEvent(new CustomEvent('openedit:studio-playhead'));
  const current = renderer, token = generation;
  if (current) { const result = await current.frame(time, {}, offsets); if (token !== generation || current !== renderer) return; geometry = result; studio.geometry = result; }
  window.dispatchEvent(new CustomEvent('openedit:studio-frame'));
  if (studio.autoKey && !form.contains(document.activeElement) && !drag) inspector();
  drawGuides();
}
function remember() {
  if (!draft) return;
  try { const key = `open_edit.studio-draft.${state.currentProjectId}.${draft.object_id}`;
    if (dirty()) sessionStorage.setItem(key, JSON.stringify({ source: source.value, baseline: draft.data.source })); else sessionStorage.removeItem(key);
  } catch {}
}
function acceptSnapshot(discard = false) {
  pendingSnapshot = true; pendingDiscard ||= discard;
  if (!snapshotTask) snapshotTask = (async () => {
    loadingSnapshot = true; controls();
    try {
      while (pendingSnapshot) {
        const discard = pendingDiscard; pendingSnapshot = false; pendingDiscard = false;
        await acceptOneSnapshot(discard);
      }
    } finally { loadingSnapshot = false; snapshotTask = null; controls(); }
  })();
  return snapshotTask;
}
async function acceptOneSnapshot(discard = false) {
  if (!panel.open || !studio.projectId || studio.projectId !== state.currentProjectId) return;
    if (lastProject !== studio.projectId) { ++generation; playing = false; time = 0; draft = null; geometry = []; el('video').removeAttribute('src'); }
    lastProject = studio.projectId;
    const documents = studio.objects.filter(o => o.kind === 'document'); el('document').replaceChildren();
    for (const doc of documents) { const option = document.createElement('option'); option.value = doc.object_id; option.textContent = doc.data.label; el('document').append(option); }
    const doc = documents.find(o => o.object_id === studio.documentId) || documents[0];
    if (!discard && draft?.saved && draft.object_id === doc?.object_id && dirty()) {
      if (draft.data.source !== doc.data.source) { draft.stale = true; message('Project changed. Your source draft is kept; reload before applying it.'); } controls(); return;
    }
    if (doc) {
      const changed = draft?.object_id !== doc.object_id || draft?.data.source !== doc.data.source || draft?.data.fps !== doc.data.fps || !renderer;
      draft = { ...doc, data: { ...doc.data }, saved: true }; studio.documentId = doc.object_id; el('document').value = doc.object_id;
      invalidateChecked(doc.data);
      source.value = doc.data.source; el('duration').value = doc.data.duration_sec; el('fps').value = doc.data.fps; el('clip-id').value = doc.data.clip_id;
      el('seek').max = doc.data.duration_sec; el('seek').step = 1 / doc.data.fps; layerLists(); if (changed) await mountDraft(); else drawGuides();
    } else if (!draft || draft.saved || discard) {
      const project = state.currentProjectId, legacy = await studioRequest('/graphics?clip_id=graphics'); if (project !== state.currentProjectId) return;
      draft = { kind: 'document', object_id: 'graphics-document', saved: false, data: { source: legacy.source, clip_id: 'graphics', track_id: 'graphics', position_sec: 0, duration_sec: 3, fps: 30, label: 'Graphics', locked_ids: [], elements: [] } };
      source.value = draft.data.source; el('duration').value = 3; el('fps').value = 30; el('clip-id').value = 'graphics'; layerLists(); await mountDraft();
    }
    if (draft && !discard && !dirty()) try {
      const saved = JSON.parse(sessionStorage.getItem(`open_edit.studio-draft.${state.currentProjectId}.${draft.object_id}`));
      if (typeof saved?.source === 'string') { source.value = saved.source; draft.stale = saved.baseline !== draft.data.source; message('Recovered source draft · save or reload to continue.'); }
    } catch {}
}
async function load(discard = false) { await loadStudio(); await acceptSnapshot(discard); }
async function save(data = { ...draft.data, source: source.value, duration_sec: Number(el('duration').value), fps: Number(el('fps').value), clip_id: el('clip-id').value }, label = 'Edit graphics source') {
  if (!draft || draft.stale) throw new Error('Reload the project before applying this draft.');
  const objectId = draft.object_id; saving = true; controls();
  try {
    await commitStudio([{ kind: 'document', object_id: objectId, data }], label);
    draft = null; studio.documentId = objectId; await acceptSnapshot(true); remember(); message(`Saved editable source · revision ${studio.revision}`);
  } finally { saving = false; controls(); }
}
async function rewrite(edits, label) {
  if (!draft || busy || studio.busy || dirty()) throw new Error('Save or reload the source draft before editing objects.');
  busy = true; controls(); playing = false;
  try { const result = await studioRequest('/studio/compile', { expected_revision: studio.revision, source: draft.data.source, edits }); await save({ ...draft.data, source: result.source }, label); }
  finally { busy = false; controls(); }
}
async function translations(offsets, label, baseline = geometry) {
  await rewrite(Object.entries(offsets).flatMap(([id, [dx, dy]]) => {
    const g = baseline.find(g => g.id === id), [x, y] = localDelta(g?.parent_matrix, dx, dy);
    const deltaX=Math.round(x*1e3)/1e3, deltaY=Math.round(y*1e3)/1e3;
    const layer=elements().find(e=>e.id===id), localTime=Math.max(0,g?.local_time_sec ?? time);
    if (studio.autoKey) return [...(deltaX?keyframeEdits(draft.data,id,'x',localTime,g.x+deltaX,'linear',layer.x || 0):[]), ...(deltaY?keyframeEdits(draft.data,id,'y',localTime,g.y+deltaY,'linear',layer.y || 0):[])];
    return [{ kind: 'translate', source: `index.tsx:${id}`, dx: deltaX, dy: deltaY }];
  }), label);
}
const pointer = event => { const rect = canvas.getBoundingClientRect(); return [(event.clientX - rect.left) * canvas.width / rect.width, (event.clientY - rect.top) * canvas.height / rect.height]; };
canvas.addEventListener('pointerdown', event => {
  if (event.button !== 0 || !draft || busy || studio.busy || dirty()) return;
  playing = false; const start = pointer(event), tool = el('tool').value;
  if (tool !== 'select') drag = { mode: 'mark', tool, points: [start, start] };
  else {
    const hit = [...geometry].reverse().find(g => g.visible && insidePolygon(start, g.corners) && visual(elements().find(e => e.id === g.id) || {})); selectMarks([]);
    if (hit) {
      if (event.shiftKey) selectObjects(studio.selectedIds.includes(hit.id) ? studio.selectedIds.filter(id => id !== hit.id) : [...studio.selectedIds, hit.id], draft.object_id);
      else if (!studio.selectedIds.includes(hit.id)) selectObjects([hit.id], draft.object_id);
      if (!studio.selectedIds.some(locked) && !event.shiftKey) drag = { mode: 'move', start, end: start, ids: roots(), originalGeometry: geometry };
    } else { if (!event.shiftKey) selectObjects([], draft.object_id); drag = { mode: 'box', start, end: start, previous: [...studio.selectedIds] }; }
  } canvas.setPointerCapture(event.pointerId); drawGuides();
});
canvas.addEventListener('pointermove', event => {
  if (!drag) return; const point = pointer(event);
  if (drag.mode === 'mark') { if (drag.tool === 'freehand') { if (drag.points.length < 1024) drag.points.push(point); } else drag.points[1] = point; drawGuides(); }
  else if (drag.mode === 'move') {
    drag.end = point; const offsets = Object.fromEntries(drag.ids.map(id => [id, localDelta(drag.originalGeometry.find(g => g.id === id)?.parent_matrix, point[0] - drag.start[0], point[1] - drag.start[1])])); seek(time, offsets).catch(fail);
  } else { drag.end = point; drawGuides(); }
});
canvas.addEventListener('pointerup', safe(async () => {
  const ended = drag; drag = null; if (!ended) return;
  if (ended.mode === 'box') {
    const box = bounds([ended.start, ended.end]), ids = geometry.filter(g => g.visible && g.corners.every(([x, y]) => x >= box.left && x <= box.right && y >= box.top && y <= box.bottom)).map(g => g.id);
    selectObjects([...new Set([...ended.previous, ...ids])], draft.object_id); drawGuides();
  } else if (ended.mode === 'move') {
    const dx = ended.end[0] - ended.start[0], dy = ended.end[1] - ended.start[1];
    if (Math.hypot(dx, dy) > .5) await translations(Object.fromEntries(ended.ids.map(id => [id, [dx, dy]])), 'Move graphics layers', ended.originalGeometry); else await seek(time);
  } else {
    const anchor = geometry.find(g => g.id === studio.selectedIds[0]), local = anchor && inverse(anchor.matrix);
    const points = ['pin', 'note'].includes(ended.tool) ? [ended.points[0]] : ended.tool === 'freehand' ? ended.points : [ended.points[0], ended.points.at(-1)], id = uid('mark');
    const changes = [{ kind: 'annotation', object_id: id, data: { tool: ended.tool, points: local ? points.map(p => transformPoint(local, p)) : points,
      coordinate_space: local ? 'object' : 'composition', anchor_id: local ? anchor.id : null, document_id: draft.object_id, target_ids: studio.selectedIds,
      anchor_sec: time + (draft.data.position_sec || 0), scope: local ? 'object' : 'frame', text: '' } }];
    if (!draft.saved) changes.unshift({ kind: 'document', object_id: draft.object_id, data: draft.data });
    await commitStudio(changes, 'Add AI mark'); selectMarks([id]); drawGuides();
  }
}));
canvas.addEventListener('pointercancel', () => { drag = null; seek(time).catch(fail); });
select.addEventListener('change', () => selectObjects([select.value], draft?.object_id));
form.addEventListener('submit', safe(async event => {
  event.preventDefault(); const selected = item(), edits = [];
  const baseline=studio.autoKey?{...selected,...geometry.find(g=>g.id===selected.id)}:selected;
  for (const id of roots()) {
    const layer = elements().find(e => e.id === id), props = {}, evaluated=geometry.find(g=>g.id===id), localTime=Math.max(0,evaluated?.local_time_sec ?? time);
    const dx = Number(form.elements.x.value) - (baseline.x || 0), dy = Number(form.elements.y.value) - (baseline.y || 0);
    if (dx || dy) {
      if (studio.autoKey) { if(dx)edits.push(...keyframeEdits(draft.data,id,'x',localTime,(evaluated?.x ?? layer.x ?? 0)+dx,'linear',layer.x || 0)); if(dy)edits.push(...keyframeEdits(draft.data,id,'y',localTime,(evaluated?.y ?? layer.y ?? 0)+dy,'linear',layer.y || 0)); }
      else edits.push({ kind: 'translate', source: `index.tsx:${id}`, dx, dy });
    }
    for (const name of ['width', 'height', 'rotation', 'scale', 'opacity', 'fontSize']) if (!form.elements[name].disabled && Number(form.elements[name].value) !== (baseline[name] ?? ({ rotation: 0, scale: 1, opacity: 1, fontSize: 48 }[name]))) props[name] = Number(form.elements[name].value);
    if (form.elements.color.value !== (selected.color ?? selected.fill ?? '#ffffff') && ['text', 'rect'].includes(layer.tag)) props[layer.tag === 'rect' ? 'fill' : 'color'] = form.elements.color.value;
    if (studio.autoKey) for (const key of ['width','height','rotation','scale','opacity']) if(Object.hasOwn(props,key)) { edits.push(...keyframeEdits(draft.data,id,key,localTime,props[key],'linear',layer[key] ?? ({scale:1,opacity:1}[key] || 0))); delete props[key]; }
    if (Object.keys(props).length) edits.push({ kind: 'set', source: `index.tsx:${id}`, props });
    if (layer.tag === 'text' && form.elements.text.value !== selected.text) edits.push({ kind: 'text', source: `index.tsx:${id}`, text: form.elements.text.value });
  } if (edits.length) await rewrite(edits, 'Edit layer properties');
}));
source.addEventListener('input', () => { remember(); controls(); message('Unsaved source draft · Save source to update the canvas.'); });
el('commit').addEventListener('click', safe(() => save()));
el('reload').addEventListener('click', safe(async () => { if (draft) try { sessionStorage.removeItem(`open_edit.studio-draft.${state.currentProjectId}.${draft.object_id}`); } catch {} await load(true); }));
el('document').addEventListener('change', safe(async () => { if (dirty()) throw new Error('Save or reload the source draft first.'); studio.documentId = el('document').value; selectObjects([], studio.documentId); draft = null; await acceptSnapshot(true); }));
el('new').addEventListener('click', safe(async () => {
  if (dirty()) throw new Error('Save or reload the source draft first.'); const view = await studioRequest('/graphics?clip_id=' + encodeURIComponent(uid('new'))), id = uid('composition');
  saving = true;
  try { await commitStudio([{ kind: 'document', object_id: id, data: { source: view.source, clip_id: uid('graphics'), track_id: uid('graphics-track'), duration_sec: 3, fps: 30, label: `Composition ${studio.objects.filter(o => o.kind === 'document').length + 1}` } }], 'Create composition'); }
  finally { saving = false; }
  studio.documentId = id; draft = null; await acceptSnapshot(true);
}));
for (const tag of ['text', 'rect']) el(`add-${tag}`).addEventListener('click', safe(async () => {
  const id = uid(tag), jsx = tag === 'text' ? `<text id="${id}" x={100} y={100} width={600} height={80} fontFamily="OpenEdit Sans" fontSize={48} color="#ffffff">New text</text>` : `<rect id="${id}" x={100} y={100} width={200} height={140} fill="#579bdf" />`;
  await rewrite([{ kind: 'insert', parent: `index.tsx:${draft.data.scene.id}`, jsx }], `Add ${tag}`); selectObjects([id], draft.object_id);
}));
el('group').addEventListener('click', safe(async () => { const id = uid('group'); await rewrite([{ kind: 'group', sources: roots().map(id => `index.tsx:${id}`), id }], 'Group layers'); selectObjects([id], draft.object_id); }));
el('duplicate').addEventListener('click', safe(() => rewrite(roots().map(id => ({ kind: 'duplicate', source: `index.tsx:${id}` })), 'Duplicate layers')));
el('delete').addEventListener('click', safe(async () => { await rewrite(roots().map(id => ({ kind: 'remove', source: `index.tsx:${id}` })), 'Delete layers'); selectObjects([], draft.object_id); }));
el('hidden').addEventListener('change', safe(() => rewrite(roots().map(id => ({ kind: 'set', source: `index.tsx:${id}`, props: { hidden: el('hidden').checked } })), 'Change layer visibility')));
el('locked').addEventListener('change', safe(async () => { const locks = new Set(draft.data.locked_ids || []); for (const id of studio.selectedIds) { if (el('locked').checked) locks.add(id); else locks.delete(id); } await save({ ...draft.data, locked_ids: [...locks] }, 'Change layer locks'); }));
for (const direction of ['forward', 'backward']) el(direction).addEventListener('click', safe(async () => {
  const selected = item(), siblings = elements().filter(e => e.parent_id === selected.parent_id && visual(e)), index = siblings.findIndex(e => e.id === selected.id), before = direction === 'backward' ? siblings[index - 1] : siblings[index + 2];
  if ((direction === 'backward' && !before) || (direction === 'forward' && index === siblings.length - 1)) return;
  await rewrite([{ kind: 'move', source: `index.tsx:${selected.id}`, parent: `index.tsx:${selected.parent_id}`, ...(before ? { before: `index.tsx:${before.id}` } : {}) }], `Move layer ${direction}`);
}));
el('align').addEventListener('change', safe(async () => { const mode = el('align').value; el('align').value = ''; if (mode) await translations(alignmentOffsets(geometry.filter(g => roots().includes(g.id)), mode, canvas.width, canvas.height), 'Align graphics layers'); }));
el('mark-properties').addEventListener('submit', safe(async event => {
  event.preventDefault(); const current = mark(), f = event.currentTarget;
  if (current) await commitStudio([{ kind: 'annotation', object_id: current.object_id, data: { ...current.data, text: f.elements.text.value, scope: f.elements.scope.value, anchor_sec: Number(f.elements.anchor_sec.value), end_sec: f.elements.end_sec.value === '' ? null : Number(f.elements.end_sec.value) } }], 'Edit AI mark');
}));
el('delete-mark').addEventListener('click', safe(async () => { const current = mark(); if (current) await commitStudio([{ kind: 'annotation', object_id: current.object_id, data: null }], 'Delete AI mark'); selectMarks([]); }));
el('convert-mark').addEventListener('click', safe(() => convertMark(mark())));
el('seek').addEventListener('input', safe(event => { playing = false; return seek(event.target.value); }));
el('play').addEventListener('click', () => {
  const token = ++playGeneration; playing = !playing; if (!playing) return; if (time >= (draft?.data.duration_sec || 3) - .05) time = 0; let last = performance.now();
  const tick = async now => {
    if (token !== playGeneration) return;
    if (!playing || !panel.open || !renderer) { playing = false; return; }
    const next = time + (now - last) / 1000; last = now;
    try { await seek(next); } catch (error) { playing = false; fail(error); return; }
    if (time >= (draft?.data.duration_sec || 3) - .001) playing = false; else requestAnimationFrame(tick);
  }; requestAnimationFrame(tick);
});
el('checked').addEventListener('change', () => { el('video').hidden = !el('checked').checked; });
el('preview').addEventListener('click', safe(async () => {
  if (dirty()) throw new Error('Save the source draft before checking the rendered preview.');
  busy = true; controls(); const project = state.currentProjectId, revision = studio.revision;
  try {
    const submitted = await studioRequest('/render', { mode: 'graphics', expected_revision: revision, graphics: { source: draft.data.source, duration_sec: draft.data.duration_sec, fps: draft.data.fps } });
    checkedJob = submitted.job_id; controls(); message('Checking full-quality graphics…'); let result;
    do { await new Promise(resolve => setTimeout(resolve, 750)); result = await studioRequest(`/render_jobs/${checkedJob}`, undefined, project); } while (['queued', 'running', 'cancelling'].includes(result.status));
    if (project !== state.currentProjectId || revision !== studio.revision) return;
    if (result.status !== 'succeeded') throw new Error(result.error || `Preview ${result.status}`);
    checkedSource = previewKey(draft.data);
    el('video').src = `/api/projects/${encodeURIComponent(project)}/graphics/${checkedJob}/preview`; el('video').load(); el('checked').checked = true; el('video').hidden = false;
    message('Checked full-quality preview · passed quality checks');
  } finally { checkedJob = null; busy = false; controls(); }
}));
el('cancel').addEventListener('click', safe(() => checkedJob && studioRequest(`/render_jobs/${checkedJob}/cancel`, {})));
panel.addEventListener('toggle', () => { if (panel.open) safe(() => load())(); else { playing = false; ++generation; renderer?.dispose(); renderer = null; } });
window.addEventListener('openedit:studio-loaded', () => { if (!saving) safe(() => acceptSnapshot())(); });
window.addEventListener('openedit:studio-selection', () => { layerLists(); drawGuides(); });
window.addEventListener('openedit:studio-busy', controls);
window.addEventListener('openedit:studio-autokey', inspector);
document.addEventListener('keydown', safe(async event => {
  if (!panel.open || event.target.closest('input, textarea, select, [contenteditable=true]') || busy || studio.busy) return;
  if (event.key === 'Escape') { drag = null; selectObjects([], draft?.object_id); selectMarks([]); await seek(time); }
  if (['Delete', 'Backspace'].includes(event.key) && studio.selectedIds.length) { event.preventDefault(); el('delete').click(); }
  const delta = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[event.key];
  if (delta && studio.selectedIds.length && !studio.selectedIds.some(locked)) { event.preventDefault(); const factor = event.shiftKey ? 10 : 1; await translations(Object.fromEntries(roots().map(id => [id, delta.map(v => v * factor)])), 'Nudge layers'); }
}));
controls();
