/* Keyframe tracks and Bezier handles edit durable source, using the shared runtime. */
import { state } from './state.js';
import { studio, studioObject, studioRequest, commitStudio } from './studio-state.js';
import { layerLocked } from './studio-geometry.js';
import { keyframeEdits, animatedProperties } from './keyframes.js';
import { showToast } from './dom.js';
const section = document.createElement('section');
section.id = 'graphics-animation';
section.className = 'studio-animation';
document.getElementById('graphics-inspector').append(section);
const doc = () => studioObject('document', studio.documentId);
const layer = () => doc()?.data.elements.find(e => e.id === studio.selectedIds[0]);
const uid = prefix => `${prefix}-${crypto.randomUUID()}`;
const safe = fn => async (...args) => {
  try {
    await fn(...args);
  } catch (error) {
    showToast(error.message, 'error');
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
    class: 'btn btn-ghost btn-xs'
  });
  b.disabled = disabled;
  b.addEventListener('click', safe(fn));
  return b;
}
function field(label, value, attrs = {}) {
  const wrap = node('label', label),
    input = node('input', undefined, attrs);
  input.value = value;
  wrap.append(input);
  return {
    wrap,
    input
  };
}
async function rewrite(edits, label) {
  const current = doc();
  if (!current) throw new Error('Add this composition to the timeline before animating it.');
  const source = current.data.source;
  if (window.document.getElementById('graphics-source').value !== source) throw new Error('Save or reload your source draft first.');
  const compiled = await studioRequest('/studio/compile', {
    expected_revision: studio.revision,
    source,
    edits
  });
  await commitStudio([{
    kind: 'document',
    object_id: current.object_id,
    data: {
      ...current.data,
      source: compiled.source
    }
  }], label);
}
let property = 'x';
function render() {
  const expanded = new Set([...section.querySelectorAll('details[open][data-keyframe-id]')].map(e=>e.dataset.keyframeId));
  section.replaceChildren(node('h3', 'Animation'));
  const auto = node('label', 'Auto-key '),
    checkbox = node('input', undefined, {
      type: 'checkbox',
      'aria-label': 'Auto-key'
    });
  checkbox.checked = studio.autoKey;
  checkbox.addEventListener('change', () => {
    studio.autoKey = checkbox.checked;
    window.dispatchEvent(new CustomEvent('openedit:studio-autokey'));
    render();
  });
  auto.append(checkbox);
  section.append(auto, node('p', studio.autoKey ? 'Property changes create a keyframe at the playhead.' : 'Auto-key off · dragging moves the whole motion path.', {
    class: 'muted small'
  }));
  const current = doc(),
    selected = layer();
  if (!current || !selected) {
    section.append(node('p', 'Save the composition and select a layer to edit animation.', {
      class: 'muted small'
    }));
    return;
  }
  const disabled = studio.busy || layerLocked(selected.id, current.data.elements, current.data.locked_ids, current.data.locked);
  const picker = node('select', undefined, {
    'aria-label': 'Animated property'
  });
  const properties = animatedProperties.filter(p => !(selected.tag === 'group' && ['width', 'height', 'color'].includes(p)) && !(selected.tag === 'image' && p === 'color'));
  if (!properties.includes(property)) property = 'x';
  for (const p of properties) picker.append(node('option', p, {
    value: p
  }));
  picker.value = property;
  picker.disabled = disabled;
  picker.addEventListener('change', () => {
    property = picker.value;
    render();
  });
  section.append(picker);
  const track = current.data.elements.find(e => e.tag === 'keyframeTrack' && e.parent_id === selected.id && e.property === property);
  const frames = track ? current.data.elements.filter(e => e.tag === 'keyframe' && e.parent_id === track.id).sort((a, b) => a.time - b.time) : [];
  const timeline = node('div', undefined, {
    class: 'keyframe-rail',
    role: 'group',
    'aria-label': `${property} keyframes`
  });
  const evaluated=studio.geometry.find(g=>g.id===selected.id), origin=evaluated?.origin_sec || 0, rate=evaluated?.playback_rate || 1;
  const duration = Math.min(60,Math.max(1/current.data.fps,(current.data.duration_sec-origin)*rate,...frames.map(f=>f.time)));
  for (const frame of frames) {
    const dot = button('◆', () => {
      const seek = window.document.getElementById('graphics-seek');
      seek.value = frame.time/rate+origin;
      seek.dispatchEvent(new Event('input'));
    }, disabled);
    dot.className = 'keyframe-dot';
    dot.style.left = `${frame.time / duration * 100}%`;
    dot.title = `${frame.time.toFixed(3)}s · ${frame.value}`;
    dot.setAttribute('aria-label', `Keyframe at ${frame.time.toFixed(3)} seconds`);
    dot.addEventListener('keydown', safe(async event => {
      if (disabled) return;
      if (event.key === 'Delete' || event.key === 'Backspace') {
        event.preventDefault();
        event.stopPropagation();
        await rewrite([{
          kind: 'remove',
          source: `index.tsx:${frame.id}`
        }], 'Delete keyframe');
      }
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault();
        event.stopPropagation();
        const time = Math.max(0, Math.min(duration, frame.time + (event.key === 'ArrowLeft' ? -1 : 1) / current.data.fps));
        await rewrite([{
          kind: 'set',
          source: `index.tsx:${frame.id}`,
          props: {
            time
          }
        }], 'Move keyframe');
      }
    }));
    let dragging,
      moved = false;
    dot.addEventListener('click', event => {
      if (moved) {
        event.stopImmediatePropagation();
        moved = false;
      }
    }, true);
    dot.addEventListener('pointerdown', event => {
      if (disabled) return;
      moved = false;
      dragging = {
        x: event.clientX,
        time: frame.time
      };
      dot.setPointerCapture(event.pointerId);
      event.preventDefault();
    });
    dot.addEventListener('pointermove', event => {
      if (!dragging) return;
      moved ||= Math.abs(event.clientX - dragging.x) > 3;
      if (!moved) return;
      const time = Math.max(0, Math.min(duration, dragging.time + (event.clientX - dragging.x) / timeline.clientWidth * duration));
      dot.style.left = `${time / duration * 100}%`;
      dot.dataset.nextTime = String(Math.min(duration, Math.round(time * current.data.fps) / current.data.fps));
    });
    dot.addEventListener('pointerup', safe(async () => {
      if (!dragging) return;
      dragging = null;
      if (!moved) return;
      const time = Number(dot.dataset.nextTime ?? frame.time);
      await rewrite([{
        kind: 'set',
        source: `index.tsx:${frame.id}`,
        props: {
          time
        }
      }], 'Move keyframe');
    }));
    dot.addEventListener('pointercancel', () => {
      dragging = null;
      dot.style.left = `${frame.time / duration * 100}%`;
    });
    timeline.append(dot);
  }
  section.append(timeline);
  const add = node('form', undefined, {
      class: 'studio-control-form'
    }),
    value = field('Value', selected[property] ?? (property === 'opacity' || property === 'scale' ? 1 : property === 'color' ? '#ffffff' : 0), {
      name: 'value',
      type: property === 'color' ? 'text' : 'number',
      step: 'any'
    });
  value.input.disabled = disabled;
  add.append(value.wrap, button('Add keyframe at playhead', () => {
    if (!add.reportValidity()) return;
    const time = Math.max(0, studio.geometry.find(g => g.id === selected.id)?.local_time_sec ?? (state.playheadSec || 0) - (current.data.position_sec || 0));
    return rewrite(keyframeEdits(current.data, selected.id, property, time, property === 'color' ? value.input.value : Number(value.input.value)), 'Add keyframe');
  }, disabled));
  section.append(add);
  for (const frame of frames) {
    const row = node('details', undefined, {
      class: 'keyframe-row',
      'data-keyframe-id': frame.id
    });
    row.open=expanded.has(frame.id);
    row.append(node('summary', `${frame.time.toFixed(3)} s · ${frame.value}`));
    const form = node('form', undefined, {
        class: 'studio-control-form'
      }),
      time = field('Time (s)', frame.time, {
        type: 'number',
        step: 1 / current.data.fps,
        min: 0,
        max: duration
      }),
      val = field('Value', frame.value, {
        type: property === 'color' ? 'text' : 'number',
        step: 'any'
      });
    const easing = node('select', undefined, {
      'aria-label': 'Segment easing'
    });
    for (const option of ['linear', 'easeIn', 'easeOut', 'easeInOut', 'cubicBezier']) easing.append(node('option', option, {
      value: option
    }));
    easing.value = frame.easing?.startsWith('cubicBezier') ? 'cubicBezier' : frame.easing || 'linear';
    const named={linear:'0,0,1,1',easeIn:'.42,0,1,1',easeOut:'0,0,.58,1',easeInOut:'.42,0,.58,1'};
    const points = (/^cubicBezier\(([^)]+)\)$/.exec(frame.easing || '')?.[1] || named[frame.easing || 'linear']).split(',').map(Number);
    const handles = points.map((v, i) => field(['X1', 'Y1', 'X2', 'Y2'][i], v, {
      type: 'number',
      step: .01,
      min: i % 2 ? -4 : 0,
      max: i % 2 ? 4 : 1
    }));
    const curve = node('canvas', undefined, {
      width: 240,
      height: 130,
      class: 'bezier-editor',
      'aria-label': 'Drag Bezier control points'
    });
    let dragHandle;
    function draw() {
      const c = curve.getContext('2d'),
        p = handles.map(h => Number(h.input.value)),
        x = v => 15 + v * 210,
        y = v => 115 - v * 100;
      c.clearRect(0, 0, 240, 130);
      c.strokeStyle = '#53697c';
      c.beginPath();
      c.moveTo(x(0), y(0));
      c.lineTo(x(p[0]), y(p[1]));
      c.moveTo(x(1), y(1));
      c.lineTo(x(p[2]), y(p[3]));
      c.stroke();
      c.strokeStyle = '#73beff';
      c.beginPath();
      c.moveTo(x(0), y(0));
      c.bezierCurveTo(x(p[0]), y(p[1]), x(p[2]), y(p[3]), x(1), y(1));
      c.stroke();
      c.fillStyle = '#ffcc55';
      for (let i = 0; i < 4; i += 2) {
        c.beginPath();
        c.arc(x(p[i]), y(p[i + 1]), 5, 0, Math.PI * 2);
        c.fill();
      }
    }
    function point(event) {
      const r = curve.getBoundingClientRect();
      return [(event.clientX - r.left) * 240 / r.width, (event.clientY - r.top) * 130 / r.height];
    }
    curve.addEventListener('pointerdown', event => {
      if (disabled) return;
      const p = point(event);
      dragHandle = [0, 2].sort((a, b) => Math.hypot(p[0] - (15 + Number(handles[a].input.value) * 210), p[1] - (115 - Number(handles[a + 1].input.value) * 100)) - Math.hypot(p[0] - (15 + Number(handles[b].input.value) * 210), p[1] - (115 - Number(handles[b + 1].input.value) * 100)))[0];
      curve.setPointerCapture(event.pointerId);
      easing.value = 'cubicBezier';
      event.preventDefault();
    });
    curve.addEventListener('pointermove', event => {
      if (dragHandle === undefined) return;
      const p = point(event);
      handles[dragHandle].input.value = Math.max(0, Math.min(1, (p[0] - 15) / 210)).toFixed(2);
      handles[dragHandle + 1].input.value = Math.max(-4, Math.min(4, (115 - p[1]) / 100)).toFixed(2);
      draw();
    });
    curve.addEventListener('pointerup', () => {
      dragHandle = undefined;
    });
    curve.addEventListener('pointercancel', () => {
      dragHandle = undefined;
    });
    handles.forEach(h => h.input.addEventListener('input', draw));
    form.append(time.wrap, val.wrap, easing, curve, ...handles.map(h => h.wrap));
    form.append(button('Update keyframe', () => {
      if (!form.reportValidity()) return;
      return rewrite([{
        kind: 'set',
        source: `index.tsx:${frame.id}`,
        props: {
          time: Number(time.input.value),
          value: property === 'color' ? val.input.value : Number(val.input.value),
          easing: easing.value === 'cubicBezier' ? `cubicBezier(${handles.map(h => Number(h.input.value)).join(',')})` : easing.value
        }
      }], 'Edit keyframe');
    }, disabled), button('Delete keyframe', () => rewrite([{
      kind: 'remove',
      source: `index.tsx:${frame.id}`
    }], 'Delete keyframe'), disabled));
    for (const input of form.elements) input.disabled = disabled;
    row.append(form);
    section.append(row);
    draw();
  }
  if (track) section.append(button('Remove property animation', () => rewrite([{
    kind: 'remove',
    source: `index.tsx:${track.id}`
  }], 'Remove animation track'), disabled));
  const presets = node('select', undefined, {
    'aria-label': 'Add animation preset'
  });
  presets.append(node('option', 'Add animation preset', {
    value: ''
  }));
  for (const p of ['fade', 'grow', 'shrink', 'slideLeft', 'slideRight', 'slideUp', 'slideDown', 'spin']) presets.append(node('option', p, {
    value: p
  }));
  presets.disabled = disabled;
  presets.addEventListener('change', safe(() => presets.value && rewrite([{
    kind: 'insert',
    parent: `index.tsx:${selected.id}`,
    jsx: `<animation id="${uid('animation')}" type="${presets.value}" phase="in" duration={0.5}/>`
  }], 'Add animation preset')));
  section.append(presets);
  for (const preset of current.data.elements.filter(e => e.parent_id === selected.id && e.tag === 'animation')) {
    const form = node('form', undefined, {
        class: 'studio-control-form'
      }),
      phase = node('select', undefined, {
        'aria-label': 'Animation phase'
      });
    for (const p of ['in', 'out']) phase.append(node('option', p, {
      value: p
    }));
    phase.value = preset.phase || 'in';
    const duration = field('Duration (s)', preset.duration ?? .5, {
        type: 'number',
        min: 0,
        max: 60,
        step: 1 / current.data.fps
      }),
      delay = field('Delay (s)', preset.delay || 0, {
        type: 'number',
        min: 0,
        max: 60,
        step: 1 / current.data.fps
      });
    form.append(node('span', preset.type), phase, duration.wrap, delay.wrap, button('Update preset', () => form.reportValidity() && rewrite([{
      kind: 'set',
      source: `index.tsx:${preset.id}`,
      props: {
        phase: phase.value,
        duration: Number(duration.input.value),
        delay: Number(delay.input.value)
      }
    }], 'Edit animation preset'), disabled), button(`Remove ${preset.type}`, () => rewrite([{
      kind: 'remove',
      source: `index.tsx:${preset.id}`
    }], 'Remove animation preset'), disabled));
    for (const input of form.elements) input.disabled = disabled;
    section.append(form);
  }
}
window.addEventListener('openedit:studio-loaded', render);
window.addEventListener('openedit:studio-selection', render);
window.addEventListener('openedit:studio-busy', render);
render();
