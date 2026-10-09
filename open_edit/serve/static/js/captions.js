/* Caption source, local fonts and reusable styles use the shared editing history. */
import { state } from './state.js';
import { studio, studioRequest, commitStudio, selectObjects, loadStudio } from './studio-state.js';
import { showToast, keepDrafts } from './dom.js';
const host = document.getElementById('caption-editor');
const uid = prefix => `${prefix}-${crypto.randomUUID()}`;
const cues = () => studio.objects.filter(o => o.kind === 'caption').sort((a, b) => a.data.start_sec - b.data.start_sec);
const styles = () => studio.objects.filter(o => o.kind === 'style');
const fonts = () => studio.objects.filter(o => o.kind === 'font');
const baseStyle = {
  font_id: null,
  font_size: 48,
  color: '#ffffff',
  background: '#00000099',
  stroke_color: '#000000',
  stroke_width: 1,
  x: .1,
  y: .78,
  width: .8,
  align: 'center'
};
let selected = null,
  selectedStyle = null;
const safe = fn => async (...args) => {
  try {
    await fn(...args);
  } catch (e) {
    showToast(e.message, 'error');
  }
};
function node(tag, text, attrs = {}) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
}
function button(text, fn, disabled = false) {
  const b = node('button', text, {
    type: 'button',
    class: 'btn btn-secondary btn-xs'
  });
  b.disabled = disabled;
  b.addEventListener('click', safe(fn));
  return b;
}
function field(parent, key, label, value, options) {
  const wrap = node('label', label),
    n = node(key === 'text' ? 'textarea' : options ? 'select' : 'input', undefined, {
      name: key
    });
  if (options) for (const [v, t] of options) n.append(node('option', t, {
    value: v
  }));else if (key !== 'text') {
    n.type = typeof value === 'number' ? 'number' : 'text';
    if (n.type === 'number') n.step = 'any';
  }
  n.value = value ?? '';
  wrap.append(n);
  parent.append(wrap);
  return n;
}
async function save(data, label = 'Edit caption', id = selected) {
  return commitStudio([{
    kind: 'caption',
    object_id: id,
    data
  }], label);
}
function choose(id) {
  selected = id;
  selectObjects([id], null);
  render();
  window.dispatchEvent(new CustomEvent('openedit:seek', {
    detail: cues().find(c => c.object_id === id)?.data.start_sec || 0
  }));
}
async function importTranscript(transcribe) {
  const project = state.currentProjectId, revision = studio.revision;
  const id = studio.selectedIds[0];
  if (!id) throw new Error('Select a media clip on the timeline first.');
  const result = await studioRequest(`/captions/from-clip/${encodeURIComponent(id)}?transcribe=${transcribe}`, {});
  if (project !== state.currentProjectId || revision !== studio.revision) throw new Error('Project changed while reading the transcript. Try again.');
  await commitStudio(result.changes, 'Create captions from transcript');
}
function render() {
  keepDrafts(host, renderPanel);
}
function renderPanel() {
  host.replaceChildren(node('h3', 'Captions'));
  const actions = node('div', undefined, {
    class: 'caption-actions'
  });
  actions.append(button('Add caption', async () => {
    selected = uid('caption');
    const start = state.playheadSec || 0;
    await save({
      text: 'Your caption',
      start_sec: start,
      end_sec: start + 2,
      style: {
        ...baseStyle
      }
    }, 'Add caption');
    selectObjects([selected], null);
  }, studio.busy));
  const upload = node('input', undefined, {
    type: 'file',
    accept: '.srt',
    hidden: ''
  });
  upload.addEventListener('change', safe(async () => {
    if (!upload.files[0]) return;
    const project = state.currentProjectId, revision = studio.revision;
    const source = await upload.files[0].text();
    if (project !== state.currentProjectId || revision !== studio.revision) throw new Error('Project changed. Select the SRT file again.');
    const result = await studioRequest('/captions/parse', {
      source
    }, project);
    if (project !== state.currentProjectId || revision !== studio.revision) throw new Error('Project changed. Select the SRT file again.');
    await commitStudio(result.changes, 'Import SRT captions');
  }));
  actions.append(button('Import SRT', () => upload.click(), studio.busy), upload);
  const download = node('a', 'Export SRT', {
    class: 'btn btn-secondary btn-xs',
    download: 'captions.srt',
    href: `/api/projects/${encodeURIComponent(state.currentProjectId)}/captions.srt`
  });
  actions.append(download);
  actions.append(button('Use transcript', () => importTranscript(false), studio.busy), button('Transcribe locally', () => importTranscript(true), studio.busy));
  host.append(actions);
  const list = node('div', undefined, {
    class: 'caption-list',
    'aria-label': 'Caption cues'
  });
  for (const cue of cues()) {
    const b = button(`${cue.data.start_sec.toFixed(2)}–${cue.data.end_sec.toFixed(2)} · ${cue.data.text.slice(0, 72)}`, () => choose(cue.object_id));
    b.dataset.captionId = cue.object_id;
    b.classList.toggle('active', selected === cue.object_id);
    list.append(b);
  }
  host.append(list);
  const cue = cues().find(c => c.object_id === selected);
  if (cue) {
    const form = node('form', undefined, {
        id: 'caption-properties',
        class: 'studio-control-form',
        'data-draft-key': `caption:${cue.object_id}`
      }),
      data = cue.data,
      fields = {};
    for (const [key, label] of [['text', 'Text'], ['start_sec', 'Start (seconds)'], ['end_sec', 'End (seconds)']]) fields[key] = field(form, key, label, data[key]);
    const styleFields = {};
    for (const [key, label] of [['font_size', 'Font size at 1080p'], ['color', 'Text color'], ['background', 'Background RGBA'], ['stroke_color', 'Outline color'], ['stroke_width', 'Outline width'], ['x', 'Left (0–1)'], ['y', 'Top (0–1)'], ['width', 'Width (0–1)']]) styleFields[key] = field(form, key, label, data.style[key]);
    styleFields.align = field(form, 'align', 'Alignment', data.style.align, [['left', 'Left'], ['center', 'Center'], ['right', 'Right']]);
    styleFields.font_id = field(form, 'font_id', 'Font', data.style.font_id || '', [['', 'OpenEdit Sans'], ...fonts().map(f => [f.data.font_id, f.data.label])]);
    const submit = node('button', 'Save caption', {
      type: 'submit',
      class: 'btn btn-primary btn-sm'
    });
    form.append(submit);
    for (const el of form.elements) el.disabled = studio.busy || data.locked;
    form.addEventListener('submit', safe(async e => {
      e.preventDefault();
      const next = {
        ...data,
        style: {
          ...data.style
        }
      };
      for (const [k, f] of Object.entries(fields)) next[k] = k === 'text' ? f.value : Number(f.value);
      for (const [k, f] of Object.entries(styleFields)) next.style[k] = typeof data.style[k] === 'number' ? Number(f.value) : f.value;
      next.style.font_id ||= null;
      await save(next);
    }));
    host.append(form);
    const ops = node('div', undefined, {
      class: 'caption-actions'
    });
    ops.append(button(data.locked ? 'Unlock' : 'Lock', () => save({
      ...data,
      locked: !data.locked
    }, 'Change caption lock'), studio.busy), button(data.enabled ? 'Hide' : 'Show', () => save({
      ...data,
      enabled: !data.enabled
    }, 'Toggle caption'), studio.busy || data.locked));
    ops.append(button('Split at playhead', async () => {
      const at = state.playheadSec || 0;
      if (at <= data.start_sec || at >= data.end_sec) throw new Error('Place the playhead inside this caption.');
      const middle = Math.max(1, Math.round(data.text.length * (at - data.start_sec) / (data.end_sec - data.start_sec))),
        space = data.text.lastIndexOf(' ', middle),
        cut = space > 0 ? space : middle;
      if (cut >= data.text.length) throw new Error('Caption needs enough text to split.');
      await commitStudio([{
        kind: 'caption',
        object_id: cue.object_id,
        data: {
          ...data,
          text: data.text.slice(0, cut).trim(),
          end_sec: at
        }
      }, {
        kind: 'caption',
        object_id: uid('caption'),
        data: {
          ...data,
          text: data.text.slice(cut).trim(),
          start_sec: at
        }
      }], 'Split caption');
    }, studio.busy || data.locked));
    const next = cues()[cues().findIndex(c => c.object_id === selected) + 1];
    ops.append(button('Merge with next', () => commitStudio([{
      kind: 'caption',
      object_id: cue.object_id,
      data: {
        ...data,
        text: data.text + ' ' + next.data.text,
        end_sec: Math.max(data.end_sec, next.data.end_sec)
      }
    }, {
      kind: 'caption',
      object_id: next.object_id,
      data: null
    }], 'Merge captions'), studio.busy || data.locked || !next || next.data.locked), button('Delete caption', () => save(null, 'Delete caption'), studio.busy || data.locked));
    host.append(ops);
    const presets = node('select', undefined, {
      'aria-label': 'Caption style'
    });
    presets.append(node('option', 'Choose saved style', {
      value: ''
    }));
    for (const s of styles()) presets.append(node('option', s.data.label, {
      value: s.object_id
    }));
    presets.disabled = studio.busy || data.locked;
    presets.value = selectedStyle || '';
    presets.addEventListener('change', safe(async () => {
      const style = styles().find(s => s.object_id === presets.value);
      selectedStyle = style?.object_id || null;
      if (style) await save({
        ...data,
        style: {
          ...style.data.caption_style
        }
      }, 'Apply caption style');
    }));
    host.append(presets);
    const savedStyle = styles().find(s => s.object_id === selectedStyle);
    const styleForm = node('form', undefined, {
      'data-draft-key': `caption-style:${cue.object_id}`
    });
    styleForm.addEventListener('submit', e => e.preventDefault());
    const name = field(styleForm, 'style_name', 'Style name', savedStyle?.data.label || 'My caption style');
    styleForm.append(button('Save reusable style', () => commitStudio([{
      kind: 'style',
      object_id: uid('style'),
      data: {
        label: name.value,
        caption_style: {
          ...data.style
        }
      }
    }], 'Save caption style'), studio.busy));
    if (savedStyle) styleForm.append(button('Update saved style', () => commitStudio([{
      kind: 'style',
      object_id: savedStyle.object_id,
      data: {
        ...savedStyle.data,
        label: name.value,
        caption_style: {
          ...data.style
        }
      }
    }], 'Edit reusable style'), studio.busy || savedStyle.data.locked), button('Delete saved style', () => commitStudio([{
      kind: 'style',
      object_id: savedStyle.object_id,
      data: null
    }], 'Delete reusable style'), studio.busy || savedStyle.data.locked));
    const img = node('img', undefined, {
      class: 'caption-style-preview',
      alt: 'Caption rendered with the export font',
      src: `/api/projects/${encodeURIComponent(state.currentProjectId)}/captions/${encodeURIComponent(cue.object_id)}/image?width=640&height=360&r=${studio.revision}`
    });
    host.append(styleForm, img);
  }
  const fontInput = node('input', undefined, {
    type: 'file',
    accept: '.ttf,.otf,.woff,.woff2',
    hidden: ''
  });
  fontInput.addEventListener('change', safe(async () => {
    const file = fontInput.files[0];
    if (!file) return;
    const project = state.currentProjectId,
      body = new FormData();
    body.append('file', file);
    body.append('label', file.name);
    body.append('expected_revision', studio.revision);
    const response = await fetch(`/api/projects/${encodeURIComponent(project)}/fonts`, {
      method: 'POST',
      body
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || result.detail || 'Font import failed');
    if (project === state.currentProjectId) {
      await loadStudio();
      window.dispatchEvent(new CustomEvent('openedit:graph-changed', {
        detail: {
          projectId: project,
          studio: true
        }
      }));
    }
  }));
  host.append(button('Import project font', () => fontInput.click(), studio.busy), fontInput);
  drawTimeline();
  paintPreview();
}
function drawTimeline() {
  const area = document.getElementById('timeline-tracks-area');
  area.querySelector('.caption-timeline-row')?.remove();
  if (!cues().length) return;
  const row = node('div', undefined, {
      class: 'caption-timeline-row'
    }),
    pps = Number(area.dataset.pixelsPerSecond) || 60;
  for (const c of cues()) {
    const b = button(c.data.text, () => choose(c.object_id));
    b.dataset.captionId = c.object_id;
    b.style.left = `${c.data.start_sec * pps}px`;
    b.style.width = `${(c.data.end_sec - c.data.start_sec) * pps}px`;
    b.title = `Caption ${c.data.start_sec}–${c.data.end_sec}`;
    row.append(b);
  }
  area.append(row);
}
const media = document.querySelector('.preview-media'),
  overlay = node('div', undefined, {
    class: 'caption-live-overlay',
    'aria-hidden': 'true'
  });
media.append(overlay);
let paintKey = '';
function paintPreview() {
  const player = document.getElementById('preview-player');
  if (state.previewChunks || !document.getElementById('preview-mode-badge').textContent.startsWith('Source')) {
    overlay.replaceChildren();
    paintKey = '';
    return;
  }
  const active = cues().filter(c => c.data.enabled && (state.playheadSec || 0) >= c.data.start_sec && (state.playheadSec || 0) < c.data.end_sec);
  const width = player.videoWidth || 1280,
    height = player.videoHeight || 720,
    scale = Math.min(media.clientWidth / width, media.clientHeight / height);
  if (!Number.isFinite(scale) || scale <= 0) return;
  const nextKey = JSON.stringify([state.currentProjectId, studio.revision, active.map(c => c.object_id), width, height, media.clientWidth, media.clientHeight]);
  if (nextKey === paintKey) return;
  paintKey = nextKey;
  overlay.replaceChildren();
  overlay.style.width = `${width * scale}px`;
  overlay.style.height = `${height * scale}px`;
  overlay.style.left = `${(media.clientWidth - width * scale) / 2}px`;
  overlay.style.top = `${(media.clientHeight - height * scale) / 2}px`;
  for (const c of active) overlay.append(node('img', undefined, {
    alt: '',
    src: `/api/projects/${encodeURIComponent(state.currentProjectId)}/captions/${encodeURIComponent(c.object_id)}/image?width=${width}&height=${height}&r=${studio.revision}`
  }));
}
for (const name of ['loaded', 'busy']) window.addEventListener(`openedit:studio-${name}`, render);
window.addEventListener('openedit:studio-selection', () => {
  const id = studio.selectedIds.find(id => cues().some(c => c.object_id === id));
  if (id) selected = id;
  render();
});
window.addEventListener('openedit:timeline-rendered', drawTimeline);
window.addEventListener('openedit:project-selected', () => {
  selected = null;
  selectedStyle = null;
  render();
});
window.addEventListener('openedit:seek', () => queueMicrotask(paintPreview));
document.getElementById('preview-player').addEventListener('timeupdate', paintPreview);
new ResizeObserver(paintPreview).observe(media);
render();
