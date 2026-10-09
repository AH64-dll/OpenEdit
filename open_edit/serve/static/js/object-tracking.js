/* Local tracking, manual corrections and independently editable following effects. */
import { state } from './state.js';
import { studio, studioRequest, loadStudio, selectObjects, commitStudio } from './studio-state.js';
import { showToast, keepDrafts } from './dom.js';

const make = (tag, text, attrs = {}) => {
  const element = document.createElement(tag);
  if (text != null) element.textContent = text;
  for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, value);
  return element;
};
const safe = fn => async () => { try { await fn(); } catch (error) { showToast(error.message, 'error'); } };
const tracks = () => studio.objects.filter(o => o.kind === 'object_track');
const clips = () => (state.currentProjectState?.timeline_full?.tracks || []).flatMap(t => t.clips);
const owner = object => clips().find(c => c.clip_id === object.data.clip_id);
const sourceTime = clip => clip.in_point_sec + (state.playheadSec || 0) - clip.position_sec;
export function sampleTrack(data, time) {
  const frames = data.frames;
  if (!data.enabled || !frames?.length || time < frames[0].time_sec - 1e-6 || time > frames.at(-1).time_sec + 1e-6) return null;
  let low = 0, high = frames.length;
  while (low < high) { const middle = (low + high) >> 1; if (frames[middle].time_sec <= time) low = middle + 1; else high = middle; }
  const a = frames[Math.max(0, low - 1)], b = frames[low];
  if (!a.valid) return null;
  if (!b || Math.abs(time - a.time_sec) < 1e-6) return a;
  if (!b.valid) return null;
  const ratio = (time - a.time_sec) / (b.time_sec - a.time_sec), result = { ...a };
  for (const key of ['x', 'y', 'width', 'height', 'confidence']) result[key] += (b[key] - a[key]) * ratio;
  return result;
}
export function paintTrackedObjects(overlay, width, height) {
  for (const object of tracks()) {
    if (!studio.selectedIds.includes(object.object_id)) continue;
    const clip = owner(object);
    if (!clip || clip.hidden || clip.asset_hash !== object.data.asset_hash) continue;
    const frame = sampleTrack(object.data, sourceTime(clip));
    const asset = state.currentProjectState?.assets?.find(a => a.asset_hash === clip.asset_hash);
    if (!frame || !asset?.width || !asset?.height) continue;
    const fit = Math.min(width / asset.width, height / asset.height), aw = asset.width * fit, ah = asset.height * fit;
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    for (const [key, value] of Object.entries({ x: (width-aw)/2 + frame.x*aw, y: (height-ah)/2 + frame.y*ah,
      width: frame.width*aw, height: frame.height*ah, fill: 'none', stroke: '#64dfbe',
      'stroke-width': width/320, 'stroke-dasharray': `${width/80} ${width/160}`, 'data-tracked-object': object.object_id })) rect.setAttribute(key, value);
    overlay.append(rect);
  }
}
const panel = make('details', null, { id: 'object-tracking-inspector', class: 'panel-section inspector' });
panel.open = true; panel.append(make('summary', 'Tracked objects'));
const controls = make('div', null, { class: 'tracking-controls' }), content = make('div'), jobs = make('div', null, { class: 'tracking-jobs' });
panel.append(controls, jobs, content); document.getElementById('right-panel').append(panel);
const clipSelect = make('select', null, { id: 'tracking-clip', 'aria-label': 'Video clip to track' });
const direction = make('select', null, { id: 'tracking-direction', 'aria-label': 'Tracking direction' });
const targetMode = make('select', null, { id: 'tracking-target-mode', 'aria-label': 'Tracking target' });
for (const [value, text] of [['foreground', 'Find foreground object in region'], ['region', 'Track the exact selected region']]) targetMode.append(make('option', text, { value }));
for (const [value, text] of [['both', 'Both directions'], ['forward', 'From selection onward'], ['backward', 'Before selection']]) direction.append(make('option', text, { value }));
const rangeStart = make('input', null, { type: 'number', step: '.01', min: 0, 'aria-label': 'Tracking start in timeline seconds', id: 'tracking-start' });
const rangeEnd = make('input', null, { type: 'number', step: '.01', min: 0, 'aria-label': 'Tracking end in timeline seconds', id: 'tracking-end' });
const row = make('div', null, { class: 'tracking-range' });
for (const [text, input] of [['Start (s)', rangeStart], ['End (s)', rangeEnd]]) { const label = make('label', text); label.append(input); row.append(label); }
const start = make('button', 'Track selected region', { type: 'button', id: 'tracking-start-button', class: 'btn btn-primary btn-sm' });
controls.append(make('p', 'Select a region around the target in the video, then track its movement locally.', { class: 'muted small' }), clipSelect, targetMode, direction, row, start);
let candidatesKey = '', contentKey = '', timer = null, polling = false, projectGeneration = 0;
function candidates() {
  const at = studio.region?.playhead_sec ?? (state.playheadSec || 0);
  return (state.currentProjectState?.timeline_full?.tracks || []).filter(t => t.kind === 'video' && !t.hidden)
    .flatMap(t => t.clips).filter(c => !c.hidden && !c.document_id && c.position_sec <= at && at < c.position_sec+c.out_point_sec-c.in_point_sec);
}
function setRange() {
  const clip = candidates().find(c => c.clip_id === clipSelect.value);
  rangeStart.value = clip?.position_sec ?? ''; rangeEnd.value = clip ? clip.position_sec+clip.out_point_sec-clip.in_point_sec : '';
}
clipSelect.addEventListener('change', setRange);
async function changed() {
  await loadStudio();
  window.dispatchEvent(new CustomEvent('openedit:graph-changed', { detail: { projectId: state.currentProjectId, studio: true } }));
}
async function edit(object, edits, label) {
  const project = state.currentProjectId;
  if (object.data.locked && !edits.every(e => e.action === 'properties' && e.values.locked === false)) throw new Error('Unlock this object first.');
  await studioRequest(`/object-tracks/${encodeURIComponent(object.object_id)}/edit`, { expected_revision: studio.revision, edits, label }, project);
  if (state.currentProjectId === project) await changed();
}
function button(parent, text, fn, disabled = false, attrs = {}) {
  const element = make('button', text, { type: 'button', class: 'btn btn-secondary btn-xs', ...attrs });
  element.disabled = disabled; element.addEventListener('click', safe(fn)); parent.append(element); return element;
}
function field(parent, key, label, value) {
  const wrapper = make('label', label), input = make('input', null, { name: key, type: typeof value === 'number' ? 'number' : 'text', step: 'any' });
  input.value = value; wrapper.append(input); parent.append(wrapper); return input;
}
start.addEventListener('click', safe(async () => {
  if (!studio.region) throw new Error('Draw a region with Select region first.');
  const project = state.currentProjectId;
  start.disabled = true;
  try {
    const result = await studioRequest('/tracking', { expected_revision: studio.revision, region: studio.region,
      clip_id: clipSelect.value, start_sec: Number(rangeStart.value), end_sec: Number(rangeEnd.value), direction: direction.value, target_mode: targetMode.value }, project);
    showToast('Tracking started. You can keep editing while it runs.', 'success');
    if (project === state.currentProjectId) await pollJobs();
    return result;
  } finally { render(); }
}));
async function pollJobs() {
  clearTimeout(timer);
  if (polling || !state.currentProjectId) return;
  polling = true;
  const project = state.currentProjectId, generation = projectGeneration;
  try {
    const result = await studioRequest('/tracking', undefined, project);
    if (generation !== projectGeneration || project !== state.currentProjectId) return;
    jobs.replaceChildren();
    for (const job of result.jobs.filter(j => j.status !== 'applied').slice(0, 8)) {
      const line = make('div', null, { class: 'tracking-job', 'data-job-id': job.job_id });
      line.append(make('span', `${job.status} · ${Math.round(job.progress*100)}%${job.error ? ` · ${job.error}` : ''}`));
      if (['queued','running'].includes(job.status)) button(line, 'Cancel', () => studioRequest(`/tracking/${job.job_id}/cancel`, {}));
      if (job.status === 'succeeded') button(line, 'Use track', async () => {
        const result = await studioRequest(`/tracking/${job.job_id}/apply`, { expected_revision: studio.revision }, project);
        if (project !== state.currentProjectId) return;
        await changed(); selectObjects([result.object_id], null); await pollJobs();
      }, false, { class: 'btn btn-primary btn-xs', 'data-apply-track': job.job_id });
      jobs.append(line);
    }
    if (result.jobs.some(j => ['queued','running'].includes(j.status))) timer = setTimeout(pollJobs, 750);
  } catch (error) { if (generation === projectGeneration) jobs.textContent = error.message; }
  finally {
    polling = false;
    if (generation !== projectGeneration && state.currentProjectId) timer = setTimeout(pollJobs, 0);
  }
}
function render() {
  const available = candidates(), key = available.map(c => c.clip_id).join('|');
  if (key !== candidatesKey) {
    candidatesKey = key; clipSelect.replaceChildren();
    for (const clip of available) clipSelect.append(make('option', clip.label || clip.clip_id, { value: clip.clip_id }));
    setRange();
  }
  start.disabled = !studio.region || !available.length || studio.busy;
  const signature = JSON.stringify([studio.projectId, studio.revision, studio.selectedIds]);
  if (signature === contentKey) return;
  contentKey = signature;
  const expanded = new Set([...content.querySelectorAll('details[open][data-detail-key]')].map(e => e.dataset.detailKey));
  keepDrafts(content, () => {
    content.replaceChildren();
    for (const object of tracks()) {
      const data = object.data, selected = studio.selectedIds.includes(object.object_id), section = make('div', null, { class: 'tracking-object', 'data-object-id': object.object_id });
      button(section, `${data.label}${data.locked ? ' · Locked' : ''}${!data.enabled ? ' · Disabled' : ''}`, () => selectObjects([object.object_id], null), false, { class: selected ? 'btn btn-primary btn-sm' : 'btn btn-secondary btn-sm' });
      section.append(make('p', `${data.frames.length} motion samples · ${data.frames.filter(f => !f.valid).length} lost · ${data.frames.filter(f => f.manual).length} manual`, { class: 'muted small' }));
      const target = owner(object);
      if (!target || target.asset_hash !== data.asset_hash) section.append(make('p', target ? 'Source changed. Track the new video source.' : 'Target clip is missing.', { class: 'export-error small' }));
      if (selected) {
        const name = field(section, 'label', 'Name', data.label);
        button(section, 'Rename', () => edit(object, [{ action: 'properties', values: { label: name.value } }], 'Rename tracked object'), data.locked);
        button(section, data.locked ? 'Unlock' : 'Lock', () => edit(object, [{ action: 'properties', values: { locked: !data.locked } }], 'Change object lock'));
        button(section, data.enabled ? 'Disable' : 'Enable', () => edit(object, [{ action: 'properties', values: { enabled: !data.enabled } }], 'Toggle tracked object'), data.locked);
        button(section, 'Delete object', () => commitStudio([{ kind: 'object_track', object_id: object.object_id, data: null }], 'Delete tracked object'), data.locked);
        const clip = owner(object), frame = clip && sampleTrack(data, sourceTime(clip));
        const correction = make('details', null, { 'data-detail-key': `${object.object_id}:correction` }); correction.append(make('summary', 'Correct position at playhead'));
        const values = {};
        const frameTime = field(correction, 'time_sec', 'Source time (s)', clip ? sourceTime(clip) : 0);
        for (const key of ['x','y','width','height']) values[key] = field(correction, key, `${key} (0–1)`, frame?.[key] ?? (key === 'width' || key === 'height' ? .2 : .1));
        correction.addEventListener('toggle', () => {
          if (!correction.open || !clip || correction.dataset.initialized) return;
          correction.dataset.initialized = 'true';
          const time = sourceTime(clip), sample = sampleTrack(data, time);
          frameTime.value = time;
          if (sample) for (const key of ['x','y','width','height']) values[key].value = sample[key];
        });
        button(correction, 'Save correction', () => edit(object, [{ action: 'set_frame', frame: { time_sec: Number(frameTime.value), x: Number(values.x.value), y: Number(values.y.value), width: Number(values.width.value), height: Number(values.height.value) } }], 'Correct tracked position'), data.locked || !clip, { 'data-correct-track': object.object_id });
        button(correction, 'Delete sample at source time', () => edit(object, [{ action: 'remove_frame', time_sec: Number(frameTime.value) }], 'Delete motion sample'), data.locked || data.frames.length === 1);
        button(correction, 'Correct from selected region', async () => {
          const region = studio.region;
          if (!region || !clip) throw new Error('Draw a new region around this object first.');
          const asset = state.currentProjectState.assets.find(a => a.asset_hash === clip.asset_hash), fit = Math.min(region.canvas_width/asset.width, region.canvas_height/asset.height);
          const aw = asset.width*fit, ah = asset.height*fit;
          await edit(object, [{ action: 'set_frame', frame: { time_sec: clip.in_point_sec+region.playhead_sec-clip.position_sec,
            x: (region.left-(region.canvas_width-aw)/2)/aw, y: (region.top-(region.canvas_height-ah)/2)/ah,
            width: (region.right-region.left)/aw, height: (region.bottom-region.top)/ah } }], 'Correct target from region');
        }, data.locked);
        button(correction, 'Retrack from selected region', async () => {
          if (!studio.region) throw new Error('Draw a region at the correction frame first.');
          await studioRequest('/tracking', { expected_revision: studio.revision, object_id: object.object_id,
            clip_id: data.clip_id, region: studio.region, label: data.label, direction: direction.value, target_mode: targetMode.value,
            start_sec: Number(rangeStart.value), end_sec: Number(rangeEnd.value) }); await pollJobs();
        }, data.locked);
        section.append(correction);
        const add = make('select', null, { 'aria-label': 'Following effect type', 'data-effect-picker': object.object_id });
        for (const kind of ['highlight','blur','pixelate','cover','label']) add.append(make('option', kind, { value: kind }));
        section.append(add);
        button(section, 'Add following effect', () => edit(object, [{ action: 'add_effect', effect: { effect_id: `effect-${crypto.randomUUID()}`, kind: add.value } }], 'Add following effect'), data.locked, { 'data-add-effect': object.object_id });
        for (const effect of data.effects) {
          const details = make('details', null, { class: 'tracked-effect', 'data-effect-id': effect.effect_id, 'data-detail-key': `${object.object_id}:${effect.effect_id}` }); details.append(make('summary', `${effect.kind}${effect.enabled ? '' : ' · Disabled'}`));
          const inputs = {};
          const kind = make('select', null, { 'aria-label': 'Effect type' });
          for (const value of ['highlight','blur','pixelate','cover','label']) kind.append(make('option', value, { value }));
          kind.value = effect.kind; details.append(kind);
          for (const [key, label] of [['text','Text'],['color','Color'],['strength','Strength / size'],['padding','Padding'],['offset_x','Horizontal offset (0–1)'],['offset_y','Vertical offset (0–1)'],['scale','Scale']]) {
            if (key === 'text' && effect.kind !== 'label') continue;
            if (key === 'color' && ['blur','pixelate'].includes(effect.kind)) continue;
            if (key === 'strength' && effect.kind === 'cover') continue;
            inputs[key] = field(details, key, label, effect[key]);
          }
          button(details, 'Apply effect changes', () => edit(object, [{ action: 'update_effect', effect_id: effect.effect_id,
            values: { kind: kind.value, ...Object.fromEntries(Object.entries(inputs).map(([key,input]) => [key, ['text','color'].includes(key) ? input.value : Number(input.value)])) } }], 'Adjust following effect'), data.locked);
          button(details, effect.enabled ? 'Disable effect' : 'Enable effect', () => edit(object, [{ action: 'update_effect', effect_id: effect.effect_id, values: { enabled: !effect.enabled } }], 'Toggle following effect'), data.locked);
          button(details, 'Delete effect', () => edit(object, [{ action: 'remove_effect', effect_id: effect.effect_id }], 'Delete following effect'), data.locked);
          section.append(details);
        }
      }
      content.append(section);
    }
    for (const details of content.querySelectorAll('details[data-detail-key]')) details.open = expanded.has(details.dataset.detailKey);
  });
}
for (const event of ['openedit:studio-loaded','openedit:studio-selection','openedit:studio-busy','openedit:snapshot']) window.addEventListener(event, render);
window.addEventListener('openedit:project-selected', () => { projectGeneration++; clearTimeout(timer); candidatesKey = ''; contentKey = ''; jobs.replaceChildren(); render(); pollJobs(); });
render();
