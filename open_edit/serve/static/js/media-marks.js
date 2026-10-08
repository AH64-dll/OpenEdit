/* Durable composition marks over the media preview, shared with external AI. */
import { state } from './state.js';
import { studio, commitStudio, selectMarks, selectObjects } from './studio-state.js';
import { bounds, annotationPoints } from './studio-geometry.js';
import { markGraphic } from './mark-graphics.js';
import { showToast } from './dom.js';
const media = document.querySelector('.preview-media'),
  player = document.getElementById('preview-player');
const make = (tag, text, attrs = {}) => {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
};
const svg = (tag, attrs = {}) => {
  const e = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
};
const safe = fn => async (...args) => {
  try {
    await fn(...args);
  } catch (e) {
    showToast(e.message, 'error');
  }
};
export async function convertMark(o, duration) {
  if (!o) throw new Error('Select an AI mark first.');
  const m = o.data,
    doc = studio.objects.find(d => d.kind === 'document' && d.object_id === m.document_id);
  const [w, h] = doc ? [doc.data.scene.width, doc.data.scene.height] : size();
  const id = `graphic-${crypto.randomUUID()}`;
  let p = m.points;
  if (m.coordinate_space === 'object') {
    if (m.document_id !== studio.documentId) throw new Error('Open this mark’s Graphics composition at the target time first.');
    p = annotationPoints(m, studio.geometry);
  }
  const data = markGraphic(m, p, w, h, duration ?? (m.end_sec ? m.end_sec - m.anchor_sec : 2), fps(), id);
  await commitStudio([{
    kind: 'document',
    object_id: id,
    data
  }], 'Convert AI mark to editable graphic');
  selectObjects([id], id);
  showToast('Graphic added to the timeline. Open Graphics to edit its layers.', 'success');
}
const uid = () => `mark-${crypto.randomUUID()}`,
  marks = () => studio.objects.filter(o => o.kind === 'annotation');
const time = () => state.playheadSec || 0,
  tracks = () => state.currentProjectState?.timeline_full?.tracks || [];
const fps = () => Math.max(1, Math.min(60, Math.round(state.currentProjectState?.assets?.find(a => a.fps)?.fps || 30)));
const size = () => {
  const asset = state.currentProjectState?.assets?.find(a => a.width && a.height);
  return [asset?.width || player.videoWidth || 1920, asset?.height || player.videoHeight || 1080];
};
const toolbar = make('div', undefined, {
    class: 'media-mark-toolbar',
    id: 'media-mark-toolbar'
  }),
  tool = make('select', undefined, {
    'aria-label': 'Video annotation tool'
  });
for (const [value, text] of [['off', 'Playback'], ['select', 'Select region'], ['move', 'Move marks'], ['rectangle', 'AI box'], ['arrow', 'AI arrow'], ['freehand', 'AI freehand'], ['pin', 'AI pin'], ['note', 'AI note']]) tool.append(make('option', text, {
  value
}));
toolbar.append(tool, make('span', 'Marks guide AI and stay out of exports.', {
  class: 'muted small'
}));
document.querySelector('.transport').before(toolbar);
const overlay = svg('svg', {
  class: 'media-mark-overlay',
  id: 'media-mark-overlay',
  'aria-label': 'Video AI annotations'
});
media.append(overlay);
const panel = make('details', undefined, {
  id: 'media-marks-inspector',
  class: 'panel-section inspector'
});
panel.open = true;
panel.append(make('summary', 'Video AI marks'));
const content = make('div');
panel.append(content);
document.getElementById('right-panel').append(panel);
let drag = null,
  region = null;
const active = o => !o.data.hidden && (o.data.scope === 'object' || (o.data.scope === 'frame' ? Math.abs(time() - o.data.anchor_sec) < 1 / fps() : time() >= o.data.anchor_sec && time() < o.data.end_sec));
function points(o) {
  return o.data.document_id ? [] : o.data.points;
}
function drawMark(m, p, id) {
  if (!p.length) return;
  const [width] = size(),
    s = width / 320,
    attrs = {
      fill: 'none',
      stroke: m.color,
      'stroke-width': s,
      'stroke-linecap': 'round',
      'data-mark-id': id
    };
  const [a, b = a] = p;
  if (m.tool === 'rectangle') {
    const r = bounds(p);
    overlay.append(svg('rect', {
      ...attrs,
      x: r.left,
      y: r.top,
      width: r.right - r.left,
      height: r.bottom - r.top
    }));
  } else if (m.tool === 'arrow') {
    overlay.append(svg('line', {
      ...attrs,
      x1: a[0],
      y1: a[1],
      x2: b[0],
      y2: b[1]
    }));
    const d = Math.atan2(b[1] - a[1], b[0] - a[0]),
      r = s * 7;
    overlay.append(svg('polyline', {
      ...attrs,
      points: [[b[0] - r * Math.cos(d - .5), b[1] - r * Math.sin(d - .5)], b, [b[0] - r * Math.cos(d + .5), b[1] - r * Math.sin(d + .5)]].map(p => p.join(',')).join(' ')
    }));
  } else if (m.tool === 'freehand') overlay.append(svg('polyline', {
    ...attrs,
    points: p.map(p => p.join(',')).join(' ')
  }));else overlay.append(svg('circle', {
    ...attrs,
    cx: a[0],
    cy: a[1],
    r: s * 4
  }));
  if (m.text) {
    const t = svg('text', {
      x: a[0] + s * 5,
      y: a[1] - s * 4,
      fill: m.color,
      'font-size': s * 9,
      'data-mark-id': id
    });
    t.textContent = m.text;
    overlay.append(t);
  }
}
function paint() {
  const [width, height] = size(),
    scale = Math.min(media.clientWidth / width, media.clientHeight / height);
  overlay.setAttribute('viewBox', `0 0 ${width} ${height}`);
  Object.assign(overlay.style, {
    width: `${width * scale}px`,
    height: `${height * scale}px`,
    left: `${(media.clientWidth - width * scale) / 2}px`,
    top: `${(media.clientHeight - height * scale) / 2}px`,
    pointerEvents: tool.value === 'off' ? 'none' : 'auto'
  });
  overlay.replaceChildren();
  for (const o of marks().filter(active)) {
    const p = points(o);
    drawMark(o.data, drag?.id === o.object_id ? drag.points : p, o.object_id);
  }
  if (drag?.mode === 'draw') drawMark({
    tool: drag.tool,
    color: '#ffcc55',
    text: ''
  }, drag.points, 'draft');
  const r = drag?.mode === 'select' ? bounds([drag.start, drag.end]) : region;
  if (r) overlay.append(svg('rect', {
    x: r.left,
    y: r.top,
    width: r.right - r.left,
    height: r.bottom - r.top,
    fill: '#55b5ff22',
    stroke: '#73beff',
    'stroke-width': width / 320
  }));
}
function button(text, fn, disabled = false) {
  const b = make('button', text, {
    type: 'button',
    class: 'btn btn-secondary btn-xs'
  });
  b.disabled = disabled;
  b.addEventListener('click', safe(fn));
  return b;
}
function field(parent, name, label, value) {
  const l = make('label', label),
    e = make(name === 'text' || name === 'points' ? 'textarea' : 'input', undefined, {
      name
    });
  if (e.tagName === 'INPUT') {
    e.type = typeof value === 'number' ? 'number' : 'text';
    e.step = 'any';
  }
  e.value = value ?? '';
  l.append(e);
  parent.append(l);
  return e;
}
function render() {
  content.replaceChildren();
  const list = make('div', undefined, {
    class: 'caption-list'
  });
  for (const o of marks()) {
    const b = button(`${o.data.hidden ? 'Hidden · ' : ''}${o.data.tool} · ${o.data.text || o.object_id}`, () => {
      selectMarks([o.object_id]);
      window.dispatchEvent(new CustomEvent('openedit:seek', {
        detail: o.data.anchor_sec
      }));
    });
    b.dataset.markId = o.object_id;
    list.append(b);
  }
  content.append(list);
  const o = marks().find(o => studio.selectedMarks.includes(o.object_id));
  if (!o) {
    content.append(make('p', 'Draw on the preview to direct an AI edit.', {
      class: 'muted small'
    }));
    paint();
    return;
  }
  const form = make('form', undefined, {
      id: 'media-mark-properties',
      class: 'studio-control-form'
    }),
    m = o.data,
    f = {};
  for (const [k, l] of [['text', 'Instruction'], ['anchor_sec', 'Start (seconds)'], ['end_sec', 'End (seconds, blank for one frame)'], ['color', 'Color']]) f[k] = field(form, k, l, m[k]);
  const scope = make('select', undefined, {
    name: 'scope',
    'aria-label': 'Mark timing'
  });
  for (const v of ['frame', 'range', 'object']) scope.append(make('option', v, {
    value: v
  }));
  scope.value = m.scope;
  form.append(scope);
  f.points = field(form, 'points', `Points in ${m.coordinate_space} coordinates`, JSON.stringify(m.points));
  const save = make('button', 'Save mark', {
    type: 'submit',
    class: 'btn btn-secondary btn-xs'
  });
  form.append(save);
  for (const e of form.elements) e.disabled = studio.busy || m.locked;
  form.addEventListener('submit', safe(async e => {
    e.preventDefault();
    await commitStudio([{
      kind: 'annotation',
      object_id: o.object_id,
      data: {
        ...m,
        text: f.text.value,
        anchor_sec: Number(f.anchor_sec.value),
        end_sec: f.end_sec.value === '' ? null : Number(f.end_sec.value),
        color: f.color.value,
        scope: scope.value,
        points: JSON.parse(f.points.value)
      }
    }], 'Edit video AI mark');
  }));
  content.append(form);
  const actions = make('div', undefined, {
    class: 'caption-actions'
  });
  actions.append(button(m.locked ? 'Unlock mark' : 'Lock mark', () => commitStudio([{
    kind: 'annotation',
    object_id: o.object_id,
    data: {
      ...m,
      locked: !m.locked
    }
  }], 'Change mark lock'), studio.busy), button(m.hidden ? 'Show mark' : 'Hide mark', () => commitStudio([{
    kind: 'annotation',
    object_id: o.object_id,
    data: {
      ...m,
      hidden: !m.hidden
    }
  }], 'Change mark visibility'), studio.busy || m.locked), button('Delete mark', async () => {
    await commitStudio([{
      kind: 'annotation',
      object_id: o.object_id,
      data: null
    }], 'Delete video AI mark');
    selectMarks([]);
  }, studio.busy || m.locked));
  content.append(actions);
  const duration = field(content, 'duration', 'Graphic duration (seconds)', m.end_sec ? m.end_sec - m.anchor_sec : 2);
  content.append(button('Convert to graphic', () => convertMark(o, Number(duration.value)), studio.busy));
  paint();
}
const pointer = e => {
  const r = overlay.getBoundingClientRect(),
    [w, h] = size();
  return [(e.clientX - r.left) * w / r.width, (e.clientY - r.top) * h / r.height];
};
overlay.addEventListener('pointerdown', e => {
  if (e.button !== 0 || studio.busy || tool.value === 'off') return;
  player.pause();
  const p = pointer(e),
    id = e.target.dataset.markId,
    o = marks().find(o => o.object_id === id);
  region = null;
  if (tool.value === 'move') {
    if (!o) return;
    selectMarks([id]);
    if (o.data.locked || o.data.coordinate_space === 'object') return;
    drag = {
      mode: 'move',
      id,
      start: p,
      points: o.data.points,
      original: o
    };
  } else if (tool.value === 'select') {
    selectMarks([]);
    drag = {
      mode: 'select',
      start: p,
      end: p
    };
  } else drag = {
    mode: 'draw',
    tool: tool.value,
    start: p,
    points: [p, p]
  };
  overlay.setPointerCapture(e.pointerId);
  paint();
});
overlay.addEventListener('pointermove', e => {
  if (!drag) return;
  const p = pointer(e);
  if (drag.mode === 'move') drag.points = drag.original.data.points.map(q => [q[0] + p[0] - drag.start[0], q[1] + p[1] - drag.start[1]]);else if (drag.mode === 'select') drag.end = p;else if (drag.tool === 'freehand') {
    if (drag.points.length < 1024 && Math.hypot(p[0] - drag.points.at(-1)[0], p[1] - drag.points.at(-1)[1]) > size()[0] / 500) drag.points.push(p);
  } else drag.points[1] = p;
  paint();
});
overlay.addEventListener('pointerup', safe(async () => {
  const d = drag;
  drag = null;
  if (!d) return;
  if (d.mode === 'move') await commitStudio([{
    kind: 'annotation',
    object_id: d.id,
    data: {
      ...d.original.data,
      points: d.points
    }
  }], 'Move video AI mark');else if (d.mode === 'select') {
    region = bounds([d.start, d.end]);
    selectMarks(marks().filter(o => active(o) && points(o).length && points(o).every(([x, y]) => x >= region.left && x <= region.right && y >= region.top && y <= region.bottom)).map(o => o.object_id));
    // The selection region is transient; choosing AI box is the durable alternative.
    state.editingRegion = {
      ...region,
      coordinate_space: 'composition',
      playhead_sec: time(),
      project_id: state.currentProjectId
    };
  } else {
    const id = uid(),
      targets = [...studio.selectedIds],
      selected = tracks().flatMap(t => t.clips).filter(c => targets.includes(c.clip_id)),
      end = selected.length ? Math.max(...selected.map(c => c.position_sec + c.out_point_sec - c.in_point_sec)) : time() + 2;
    await commitStudio([{
      kind: 'annotation',
      object_id: id,
      data: {
        tool: d.tool,
        points: ['pin', 'note'].includes(d.tool) ? [d.points[0]] : d.points,
        text: '',
        target_ids: targets,
        anchor_sec: time(),
        end_sec: Math.max(time() + 1 / fps(), end),
        scope: 'range',
        coordinate_space: 'composition'
      }
    }], 'Add video AI mark');
    selectMarks([id]);
  }
  render();
}));
overlay.addEventListener('pointercancel', () => {
  drag = null;
  paint();
});
tool.addEventListener('change', paint);
for (const event of ['openedit:studio-loaded', 'openedit:studio-selection', 'openedit:studio-busy']) window.addEventListener(event, render);
for (const event of ['openedit:seek', 'openedit:studio-playhead', 'openedit:snapshot']) window.addEventListener(event, () => queueMicrotask(paint));
window.addEventListener('openedit:project-selected', () => {
  drag = null;
  region = null;
  state.editingRegion = null;
  tool.value = 'off';
  render();
});
player.addEventListener('timeupdate', paint);
player.addEventListener('loadedmetadata', paint);
new ResizeObserver(paint).observe(media);
render();
