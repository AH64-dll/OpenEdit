/* Manual timeline and effect tools write the same revision-checked IR as AI. */
import { state } from './state.js';
import { studio, commitStudio, selectObjects, loadStudio } from './studio-state.js';
import { showToast } from './dom.js';
const area = document.getElementById('timeline-tracks-area');
const labels = document.getElementById('timeline-track-labels');
const uid = prefix => `${prefix}-${crypto.randomUUID()}`;
const timeline = () => state.currentProjectState?.timeline_full || state.currentProjectState?.timeline || {
  tracks: []
};
const tracks = () => timeline().tracks || [];
const clips = () => tracks().flatMap(t => t.clips || []);
const clipById = id => clips().find(c => c.clip_id === id);
const trackById = id => tracks().find(t => t.track_id === id);
const frame = () => 1 / (Number(state.currentProjectState?.fps) || 30);
const round = value => Math.round(value / frame()) * frame();
const isLocked = clip => clip.locked || trackById(clip.track_id)?.locked || studio.objects.some(o => o.kind === 'document' && o.object_id === clip.document_id && o.data.locked);
let owner = null,
  drag = null,
  capabilities = [],
  saving = false,
  suppressClick = false;
const safe = fn => async (...args) => {
  try {
    await fn(...args);
  } catch (error) {
    showToast(error.message, 'error');
  }
};
async function commit(ops, label) {
  saving = true;
  renderInspector();
  try {
    return await commitStudio([], label, ops);
  } finally {
    saving = false;
    renderInspector();
  }
}
function node(tag, text, attrs = {}) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  for (const [name, value] of Object.entries(attrs)) element.setAttribute(name, value);
  return element;
}
function button(text, action, disabled = false) {
  const element = node('button', text, {
    type: 'button',
    class: 'btn btn-ghost btn-xs'
  });
  element.disabled = disabled;
  element.addEventListener('click', safe(action));
  return element;
}
function input(label, value, options = {}) {
  const wrap = node('label', label),
    field = node('input', undefined, {
      ...options
    });
  field.value = value ?? '';
  wrap.append(field);
  return {
    wrap,
    field
  };
}
function selectClip(id, additive = false) {
  owner = {
    kind: 'clip',
    id
  };
  selectObjects(additive ? studio.selectedIds.includes(id) ? studio.selectedIds.filter(x => x !== id) : [...studio.selectedIds.filter(clipById), id] : [id], null);
  decorateSelection();
  renderInspector();
}
function decorateSelection() {
  for (const el of area.querySelectorAll('[data-clip-id]')) el.classList.toggle('studio-selected', studio.selectedIds.includes(el.dataset.clipId));
}
function decorateTimeline() {
  for (const el of area.querySelectorAll('.timeline-clip')) {
    const clip = clipById(el.dataset.clipId);
    if (!clip) continue;
    el.classList.toggle('studio-locked', !!isLocked(clip));
    el.classList.toggle('studio-muted', !!clip.muted);
    if (!el.querySelector('.clip-trim')) for (const edge of ['in', 'out']) {
      const handle = node('span', '', {
        class: `clip-trim clip-trim-${edge}`,
        'data-trim': edge,
        'aria-label': `Trim ${edge}`
      });
      el.append(handle);
    }
  }
  for (const row of labels.querySelectorAll('[data-track-id]')) {
    const track = trackById(row.dataset.trackId);
    if (!track) continue;
    const actions = node('span', undefined, {
      class: 'track-actions'
    });
    for (const [key, text, title] of [['muted', 'M', 'Mute audio'], ['solo', 'S', 'Solo track audio'], ['hidden', 'H', 'Hide track picture'], ['locked', 'L', 'Lock track']]) {
      const b = button(text, async () => commit([{
        kind: 'set_track_properties',
        track_id: track.track_id,
        [key]: !track[key]
      }], `Change track ${key}`), saving || track.locked && key !== 'locked');
      b.title = title;
      b.setAttribute('aria-pressed', String(!!track[key]));
      b.addEventListener('click', event => event.stopPropagation());
      actions.append(b);
    }
    row.append(actions);
    row.tabIndex = 0;
    row.addEventListener('click', () => {
      owner = {
        kind: 'track',
        id: track.track_id
      };
      selectObjects([track.track_id], null);
      renderInspector();
    });
  }
  decorateSelection();
}
area.addEventListener('pointerdown', event => {
  suppressClick = false;
  const el = event.target.closest('.timeline-clip'),
    clip = clipById(el?.dataset.clipId);
  if (!clip || event.button !== 0 || studio.busy || saving) return;
  if (!studio.selectedIds.includes(clip.clip_id) || event.shiftKey) selectClip(clip.clip_id, event.shiftKey);
  if (isLocked(clip)) return;
  const selected = studio.selectedIds.map(clipById).filter(Boolean);
  if (selected.some(isLocked)) return;
  drag = {
    el,
    clip,
    selected,
    x: event.clientX,
    y: event.clientY,
    edge: event.target.dataset.trim,
    active: false,
    position: clip.position_sec,
    sourceIn: clip.in_point_sec,
    sourceOut: clip.out_point_sec,
    trackId: clip.track_id,
    pps: Number(area.dataset.pixelsPerSecond) || 60
  };
  el.setPointerCapture(event.pointerId);
  event.stopPropagation();
}, true);
area.addEventListener('pointermove', event => {
  if (!drag) return;
  const d = drag,
    dx = event.clientX - d.x;
  if (!d.active && Math.hypot(dx, event.clientY - d.y) < 4) return;
  d.active = true;
  event.preventDefault();
  let position = round(Math.max(0, d.clip.position_sec + dx / d.pps));
  const points = [state.playheadSec || 0, ...clips().filter(c => !d.selected.includes(c)).flatMap(c => [c.position_sec, c.position_sec + c.out_point_sec - c.in_point_sec])];
  if (!event.altKey) {
    const closest = points.sort((a, b) => Math.abs(a - position) - Math.abs(b - position))[0];
    if (Math.abs(closest - position) * d.pps < 8) position = round(closest);
  }
  if (d.edge === 'in') {
    const delta = Math.max(-d.clip.in_point_sec, Math.min(d.clip.out_point_sec - d.clip.in_point_sec - frame(), position - d.clip.position_sec));
    d.position = d.clip.position_sec + delta;
    d.sourceIn = d.clip.in_point_sec + delta;
  } else if (d.edge === 'out') d.sourceOut = Math.max(d.clip.in_point_sec + frame(), round(d.clip.out_point_sec + dx / d.pps));else {
    d.position = Math.max(position, d.clip.position_sec - Math.min(...d.selected.map(c => c.position_sec)));
    const row = document.elementsFromPoint(event.clientX, event.clientY).map(el => el.closest('.timeline-track-row')).find(Boolean);
    if (row?.dataset.trackKind === d.clip.track_kind) d.trackId = row.dataset.trackId;
  }
  const duration = d.sourceOut - d.sourceIn;
  d.el.style.left = `${d.position * d.pps}px`;
  d.el.style.width = `${duration * d.pps}px`;
  d.el.title = `${d.position.toFixed(3)} s · ${duration.toFixed(3)} s`;
});
area.addEventListener('pointerup', safe(async event => {
  const d = drag;
  drag = null;
  if (!d?.active) return;
  suppressClick = true;
  event.preventDefault();
  event.stopPropagation();
  const ops = d.edge ? [{
    kind: 'trim_clip',
    clip_id: d.clip.clip_id,
    new_in_point_sec: d.sourceIn,
    new_out_point_sec: d.sourceOut
  }, ...(d.position !== d.clip.position_sec ? [{
    kind: 'move_clip',
    clip_id: d.clip.clip_id,
    new_track_id: d.clip.track_id,
    new_position_sec: d.position
  }] : [])] : d.selected.map(c => ({
    kind: 'move_clip',
    clip_id: c.clip_id,
    new_track_id: c.track_id === d.clip.track_id ? d.trackId : c.track_id,
    new_position_sec: c.position_sec + d.position - d.clip.position_sec
  }));
  try {
    await commit(ops, d.edge ? 'Trim clip' : 'Move selected clips');
  } catch (error) {
    d.el.style.left = `${d.clip.position_sec * d.pps}px`;
    d.el.style.width = `${(d.clip.out_point_sec - d.clip.in_point_sec) * d.pps}px`;
    throw error;
  }
}), true);
area.addEventListener('pointercancel', () => {
  if (drag) {
    drag.el.style.left = `${drag.clip.position_sec * drag.pps}px`;
    drag.el.style.width = `${(drag.clip.out_point_sec - drag.clip.in_point_sec) * drag.pps}px`;
  }
  drag = null;
});
area.addEventListener('click', event => {
  if (suppressClick) {
    suppressClick = false;
    event.preventDefault();
    event.stopImmediatePropagation();
    return;
  }
  const el = event.target.closest('[data-clip-id]');
  if (el && !event.shiftKey) selectClip(el.dataset.clipId);
}, true);
const inspector = node('section', undefined, {
  id: 'timeline-inspector',
  class: 'panel-section inspector'
});
document.getElementById('clip-inspector').after(inspector);
async function removeSelected(ripple = false) {
  const selected = studio.selectedIds.map(clipById).filter(Boolean).sort((a, b) => b.position_sec - a.position_sec);
  if (!selected.length) return;
  await commit(selected.map(c => ({
    kind: ripple ? 'ripple_delete_clip' : 'remove_clip',
    clip_id: c.clip_id
  })), ripple ? 'Ripple delete clips' : 'Delete clips');
  selectObjects([], null);
  owner = null;
}
function renderInspector() {
  inspector.replaceChildren(node('h3', owner?.kind === 'track' ? 'Track & effects' : 'Timeline & effects'));
  const target = owner?.kind === 'clip' ? clipById(owner.id) : owner?.kind === 'track' ? trackById(owner.id) : null;
  if (!target) {
    inspector.append(node('p', 'Select a clip or track to edit.', {
      class: 'muted small'
    }));
    return;
  }
  const disabled = saving || studio.busy || (owner.kind === 'clip' ? isLocked(target) : target.locked);
  const props = node('form', undefined, {
    class: 'studio-control-form'
  });
  const name = input('Name', target.label, {
    maxlength: 256
  });
  props.append(name.wrap);
  if (owner.kind === 'clip') {
    const start = input('Start (seconds)', target.position_sec, {
        type: 'number',
        min: 0,
        step: 'any'
      }),
      sourceIn = input('Source in (seconds)', target.in_point_sec, {
        type: 'number',
        min: 0,
        step: 'any'
      }),
      sourceOut = input('Source out (seconds)', target.out_point_sec, {
        type: 'number',
        min: 0,
        step: 'any'
      });
    props.append(start.wrap, sourceIn.wrap, sourceOut.wrap, button('Apply timing', () => commit([{
      kind: 'trim_clip',
      clip_id: target.clip_id,
      new_in_point_sec: Number(sourceIn.field.value),
      new_out_point_sec: Number(sourceOut.field.value)
    }, {
      kind: 'move_clip',
      clip_id: target.clip_id,
      new_track_id: target.track_id,
      new_position_sec: Number(start.field.value)
    }], 'Edit clip timing'), disabled));
  }
  const flags = {};
  for (const key of ['locked', 'muted', 'hidden']) {
    const f = input(key[0].toUpperCase() + key.slice(1), '', {
      type: 'checkbox'
    });
    f.field.checked = !!target[key];
    f.field.disabled = disabled && key !== 'locked';
    flags[key] = f.field;
    props.append(f.wrap);
  }
  props.append(button('Apply properties', () => {
    const op = {
      kind: owner.kind === 'clip' ? 'set_clip_properties' : 'set_track_properties',
      [`${owner.kind}_id`]: owner.id
    };
    if (target.locked && !flags.locked.checked) op.locked = false;else {
      op.label = name.field.value;
      for (const [key, field] of Object.entries(flags)) op[key] = field.checked;
    }
    return commit([op], `Edit ${owner.kind} properties`);
  }, saving || studio.busy));
  inspector.append(props);
  const actions = node('div', undefined, {
    class: 'studio-layer-actions'
  });
  if (owner.kind === 'clip') {
    actions.append(button('Split at playhead', async () => {
      const at = round(state.playheadSec || 0),
        end = target.position_sec + target.out_point_sec - target.in_point_sec;
      if (at <= target.position_sec || at >= end) throw new Error('Place the playhead inside this clip to split it.');
      const left = uid('clip'),
        right = uid('clip');
      await commit([{
        kind: 'split_clip',
        clip_id: target.clip_id,
        at_sec: at,
        left_clip_id: left,
        right_clip_id: right
      }], 'Split clip');
      owner = {
        kind: 'clip',
        id: left
      };
      selectObjects([left], null);
    }, disabled), button('Duplicate', async () => {
      const id = uid('clip');
      await commit([{
        kind: 'duplicate_clip',
        clip_id: target.clip_id,
        new_clip_id: id,
        position_sec: target.position_sec + target.out_point_sec - target.in_point_sec,
        effect_ids: Object.fromEntries(target.effects.map(e => [e.effect_id, uid('effect')]))
      }], 'Duplicate clip');
      owner = {
        kind: 'clip',
        id
      };
      selectObjects([id], null);
    }, disabled), button('Delete', () => removeSelected(false), disabled), button('Ripple delete', () => removeSelected(true), disabled));
  } else {
    const index = tracks().findIndex(t => t.track_id === target.track_id);
    for (const [text, next] of [['Lower layer', index - 1], ['Raise layer', index + 1]]) actions.append(button(text, () => commit([{
      kind: 'set_track_properties',
      track_id: target.track_id,
      index: next
    }], 'Reorder track'), disabled || next < 0 || next >= tracks().length));
    actions.append(button('Remove empty track', () => commit([{
      kind: 'remove_track',
      track_id: target.track_id
    }], 'Remove track'), disabled || target.clips.length > 0 || target.effects.length > 0));
  }
  inspector.append(actions);
  if (owner.kind === 'clip' && target.track_kind === 'video' && !target.document_id) {
    const next = tracks().find(t => t.track_id === target.track_id)?.clips.find(c => c.clip_id !== target.clip_id && !c.document_id && Math.abs(c.position_sec - target.position_sec - target.out_point_sec + target.in_point_sec) < .000001);
    if (next && !target.effects.some(e => e.params.layout === 'centered')) {
      const kind = node('select', undefined, {
        'aria-label': 'New visual transition'
      });
      for (const value of ['dissolve', 'wipe', 'cut']) kind.append(node('option', value, {
        value
      }));
      const duration = input('Transition duration (seconds)', Math.min(.5, target.out_point_sec - target.in_point_sec, next.out_point_sec - next.in_point_sec), {
        type: 'number',
        min: .01,
        max: 30,
        step: 'any'
      });
      inspector.append(kind, duration.wrap, button('Add visual transition', () => commit([{
        kind: 'add_transition',
        edit_id: uid('cut'),
        clip_a_id: target.clip_id,
        clip_b_id: next.clip_id,
        transition_type: kind.value,
        duration_sec: Number(duration.field.value),
        layout: 'centered'
      }], 'Add visual transition'), disabled || isLocked(next)));
    }
  }
  const add = node('select', undefined, {
    'aria-label': 'Add effect'
  });
  add.append(node('option', 'Choose an effect', {
    value: ''
  }));
  for (const spec of capabilities.filter(s => s.target_kind.includes(owner.kind))) add.append(node('option', spec.name, {
    value: spec.name
  }));
  add.disabled = disabled;
  add.addEventListener('change', safe(async () => {
    const spec = capabilities.find(s => s.name === add.value);
    if (!spec) return;
    await commit([{
      kind: 'add_effect',
      effect_id: uid('effect'),
      effect_type: spec.name,
      target_kind: owner.kind,
      target_id: owner.id,
      params: Object.fromEntries(Object.entries(spec.params).filter(([, p]) => p.default !== null).map(([k, p]) => [k, p.default]))
    }], `Add ${spec.name}`);
  }));
  inspector.append(add);
  target.effects.forEach((effect, index) => renderEffect(effect, index, target.effects.length, disabled));
}
function renderEffect(effect, index, count, disabled) {
  const spec = capabilities.find(s => s.name === effect.effect_type),
    box = node('details', undefined, {
      class: 'effect-card',
      'data-effect-id': effect.effect_id
    });
  box.open = true;
  box.append(node('summary', `${index + 1}. ${effect.effect_type}${effect.enabled === false ? ' · bypassed' : ''}`));
  if (effect.effect_type.startsWith('transition_')) {
    if (effect.params.layout === 'centered') {
      const type = node('select', undefined, {
        'aria-label': 'Visual transition type'
      });
      for (const value of ['dissolve', 'wipe', 'fade', 'luma', 'cut']) type.append(node('option', value, {
        value
      }));
      type.value = effect.effect_type.slice('transition_'.length);
      const duration = input('Duration (seconds)', effect.params.duration_sec, {
        type: 'number',
        min: .01,
        max: 30,
        step: 'any'
      });
      box.append(type, duration.wrap, button('Update transition', () => commit([{
        kind: 'set_transition_property',
        transition_id: effect.effect_id,
        prop_name: 'type',
        value: type.value
      }, {
        kind: 'set_transition_property',
        transition_id: effect.effect_id,
        prop_name: 'duration_sec',
        value: duration.field.value
      }], 'Edit visual transition'), disabled), button(effect.enabled === false ? 'Enable transition' : 'Bypass transition', () => commit([{
        kind: 'set_transition_property',
        transition_id: effect.effect_id,
        prop_name: 'enabled',
        value: String(effect.enabled === false)
      }], 'Toggle visual transition'), disabled));
      box.append(node('p', 'Keeps the cut and trims. Boundary frames freeze through the blend; audio keeps its own fades.', {
        class: 'muted small'
      }));
    }
    box.append(node('p', 'Transition between clips', {
      class: 'muted small'
    }), button('Remove transition', () => commit([{
      kind: 'remove_transition',
      transition_id: effect.effect_id
    }], 'Remove transition'), disabled));
    inspector.append(box);
    return;
  }
  const op = extras => ({
    kind: 'control_effect',
    target_kind: owner.kind,
    target_id: owner.id,
    effect_id: effect.effect_id,
    ...extras
  });
  const actions = node('div', undefined, {
    class: 'effect-actions'
  });
  actions.append(button(effect.enabled === false ? 'Enable' : 'Bypass', () => commit([op({
    enabled: effect.enabled === false
  })], 'Toggle effect'), disabled), button('↑', () => commit([op({
    action: 'move',
    index: index - 1
  })], 'Reorder effect'), disabled || index === 0), button('↓', () => commit([op({
    action: 'move',
    index: index + 1
  })], 'Reorder effect'), disabled || index === count - 1), button('Duplicate', () => commit([op({
    action: 'duplicate',
    new_effect_id: uid('effect')
  })], 'Duplicate effect'), disabled), button('Reset', () => commit([op({
    action: 'reset'
  })], 'Reset effect'), disabled || !spec), button('Delete', () => commit([op({
    action: 'remove'
  })], 'Delete effect'), disabled));
  box.append(actions);
  if (!spec) box.append(node('p', 'Advanced effect: parameter source is retained.', {
    class: 'muted small'
  }));else {
    const fields = {},
      form = node('form', undefined, {
        class: 'studio-control-form'
      });
    for (const [key, p] of Object.entries(spec.params)) {
      const f = input(`${key}${p.unit ? ` (${p.unit})` : ''}`, effect.params[key] ?? p.default, {
        name: key,
        type: p.type === 'bool' ? 'checkbox' : p.type === 'str' ? 'text' : 'number',
        ...(p.type === 'float' ? {
          step: 'any'
        } : p.type === 'int' ? {
          step: 1
        } : {}),
        ...(p.range ? {
          min: p.range[0],
          max: p.range[1]
        } : {})
      });
      if (p.type === 'bool') f.field.checked = !!(effect.params[key] ?? p.default);
      f.field.disabled = disabled;
      fields[key] = f.field;
      form.append(f.wrap);
    }
    form.append(button('Update effect', () => {
      if (!form.reportValidity()) return;
      const params = Object.fromEntries(Object.entries(fields).map(([k, f]) => [k, spec.params[k].type === 'bool' ? f.checked : spec.params[k].type === 'str' ? f.value : Number(f.value)]));
      return commit([op({
        params
      })], `Edit ${effect.effect_type}`);
    }, disabled));
    box.append(form);
  }
  if (spec?.keyframe_params?.length) renderEffectKeyframes(box, effect, spec, disabled);
  inspector.append(box);
}
function renderEffectKeyframes(box, effect, spec, disabled) {
  const target = owner.kind === 'clip' ? clipById(owner.id) : trackById(owner.id);
  const origin = owner.kind === 'clip' ? target.in_point_sec : 0;
  const end = owner.kind === 'clip' ? target.out_point_sec : timeline().duration_sec;
  const section = node('details', undefined, {
    class: 'effect-keyframes'
  });
  section.append(node('summary', 'Parameter animation'));
  const select = node('select', undefined, {
    'aria-label': 'Animated effect parameter'
  });
  for (const param of spec.keyframe_params) select.append(node('option', param, {
    value: param
  }));
  section.append(select);
  const content = node('div');
  section.append(content);
  box.append(section);
  function paint() {
    const param = select.value,
      model = spec.params[param],
      keys = effect.keyframes[param] || [];
    content.replaceChildren();
    const write = (next, label) => commit([{
      kind: 'set_keyframe',
      effect_id: effect.effect_id,
      param,
      keyframes: next.sort((a, b) => a[0] - b[0])
    }], label);
    const row = (key, index) => {
      const form = node('form', undefined, {
        class: 'studio-control-form'
      });
      const time = input('Time in owner (s)', key[0] - origin, {
        name: 'time',
        type: 'number',
        min: 0,
        max: Math.max(0, end - origin),
        step: 'any'
      });
      const value = input(`${param}${model.unit ? ` (${model.unit})` : ''}`, key[1], {
        name: 'value',
        type: 'number',
        step: 'any',
        ...(model.range ? {
          min: model.range[0],
          max: model.range[1]
        } : {})
      });
      const easing = node('select', undefined, {
        'aria-label': 'Effect keyframe interpolation'
      });
      for (const kind of spec.interp) easing.append(node('option', kind, {
        value: kind
      }));
      easing.value = key[2];
      for (const n of [time.field, value.field, easing]) n.disabled = disabled;
      form.append(time.wrap, value.wrap, easing, button(index < 0 ? 'Add effect keyframe' : 'Update effect keyframe', () => {
        if (!form.reportValidity()) return;
        const at = Number(time.field.value) + origin;
        const next = keys.filter((k, i) => i !== index && Math.abs(k[0] - at) > frame() / 2);
        next.push([at, Number(value.field.value), easing.value]);
        return write(next, 'Edit effect keyframes');
      }, disabled));
      if (index >= 0) form.append(button('Delete keyframe', () => write(keys.filter((_, i) => i !== index), 'Delete effect keyframe'), disabled));
      content.append(form);
    };
    keys.forEach(row);
    row([Math.max(origin, Math.min(end, owner.kind === 'clip' ? origin + (state.playheadSec || 0) - target.position_sec : state.playheadSec || 0)), effect.params[param] ?? model.default ?? 0, spec.interp[0] || 'linear'], -1);
    if (keys.length) content.append(button('Remove parameter animation', () => write([], 'Remove effect animation'), disabled));
  }
  select.addEventListener('change', paint);
  paint();
}
window.addEventListener('openedit:timeline-rendered', decorateTimeline);
window.addEventListener('openedit:snapshot', () => {
  decorateSelection();
  renderInspector();
});
window.addEventListener('openedit:studio-selection', decorateSelection);
window.addEventListener('openedit:project-selected', () => {
  owner = null;
  renderInspector();
});
window.addEventListener('openedit:inspect-clip', event => {
  owner = {
    kind: 'clip',
    id: event.detail.clipId
  };
  renderInspector();
});
area.addEventListener('keydown', safe(async event => {
  if (event.key === 'Delete' || event.key === 'Backspace') {
    event.preventDefault();
    await removeSelected(event.shiftKey);
  }
}));
const toolbar = node('div', undefined, {
  class: 'timeline-create-tracks'
});
for (const kind of ['video', 'audio']) toolbar.append(button(`+ ${kind} track`, async () => {
  if (studio.projectId !== state.currentProjectId) await loadStudio();
  await commit([{
    kind: 'set_track_properties',
    track_id: uid(kind),
    track_kind: kind,
    label: `${kind === 'video' ? 'Video' : 'Audio'} ${tracks().filter(t => t.kind === kind).length + 1}`
  }], `Add ${kind} track`);
}));
// Replace the existing 20px ruler spacer so track rows remain aligned.
window.addEventListener('openedit:timeline-rendered', () => labels.firstElementChild?.replaceWith(toolbar));
fetch('/api/studio/effects').then(r => r.json()).then(r => {
  capabilities = r.effects;
  renderInspector();
}).catch(() => {});
