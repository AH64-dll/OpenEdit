/* Accessible persistent panel sizes and provider-independent AI context. */
import { state } from './state.js';
import { studio, editingContext, commitStudio, selectMarks } from './studio-state.js';
import { showToast } from './dom.js';

function divider(host, side, property, initial, min, max) {
  const button = document.createElement('button'); button.type = 'button';
  const horizontal = side === 'timeline';
  button.className = `studio-divider ${horizontal ? 'horizontal' : 'vertical'} ${side}`;
  button.setAttribute('role', 'separator'); button.setAttribute('aria-label', `Resize ${side} panel`);
  button.setAttribute('aria-orientation', horizontal ? 'horizontal' : 'vertical');
  let value = initial;
  try { value = Number(localStorage.getItem(`open_edit.panel.${side}`)) || initial; } catch {}
  function set(next) {
    value = Math.max(min, Math.min(max, next)); document.documentElement.style.setProperty(property, `${value}px`);
    button.setAttribute('aria-valuenow', String(Math.round(value))); button.setAttribute('aria-valuemin', String(min)); button.setAttribute('aria-valuemax', String(max));
  }
  set(value); let drag;
  const remember = () => { try { localStorage.setItem(`open_edit.panel.${side}`, String(value)); } catch {} };
  button.addEventListener('pointerdown', event => { drag = { start: horizontal ? event.clientY : event.clientX, value }; button.setPointerCapture(event.pointerId); event.preventDefault(); });
  button.addEventListener('pointermove', event => { if (!drag) return; const delta = (horizontal ? event.clientY : event.clientX) - drag.start; set(drag.value + delta * (side === 'left' ? 1 : -1)); });
  button.addEventListener('pointerup', () => { drag = null; remember(); });
  button.addEventListener('pointercancel', () => { drag = null; remember(); });
  button.addEventListener('keydown', event => {
    const direction = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -1, ArrowDown: 1 }[event.key];
    if (direction) { event.preventDefault(); set(value + direction * (side === 'left' ? 1 : -1) * (event.shiftKey ? 40 : 10)); remember(); }
  }); host.append(button);
}
document.addEventListener('DOMContentLoaded', () => {
  divider(document.getElementById('left-panel'), 'left', '--studio-left', 240, 180, 480);
  divider(document.getElementById('right-panel'), 'right', '--studio-right', 280, 240, 600);
  divider(document.getElementById('timeline-panel'), 'timeline', '--studio-timeline', 190, 120, 500);
  const dock = document.createElement('details'); dock.className = 'studio-ai-dock'; dock.open = true; dock.id = 'studio-ai-dock';
  const heading = document.createElement('summary'); heading.textContent = 'AI editing'; dock.append(heading);
  const hint = document.createElement('p'); hint.className = 'muted small'; hint.textContent = 'Select a clip or region, then describe the change.'; dock.append(hint);
  const summary = document.createElement('p'); summary.id = 'studio-ai-selection'; summary.setAttribute('role', 'status'); dock.append(summary);
  const buttons = document.createElement('div'); buttons.className = 'studio-ai-actions';
  const copy = document.createElement('button'); copy.type = 'button'; copy.className = 'btn btn-secondary btn-xs'; copy.textContent = 'Copy for AI'; copy.id = 'studio-copy-context';
  const inspect = document.createElement('button'); inspect.type = 'button'; inspect.className = 'btn btn-ghost btn-xs'; inspect.textContent = 'Inspect selection';
  const context = document.createElement('pre'); context.className = 'studio-ai-context'; context.hidden = true;
  const run = async copyText => { try { const result = await editingContext(); const text = JSON.stringify(result, null, 2); context.textContent = text;
    if (copyText) { await navigator.clipboard.writeText(text); showToast('AI context copied.', 'success'); } else context.hidden = !context.hidden;
  } catch (error) { showToast(error.message, 'warn'); } };
  copy.addEventListener('click', () => run(true)); inspect.addEventListener('click', () => run(false)); buttons.append(copy, inspect); dock.append(buttons, context);
  for (const id of ['chat-log', 'chat-status']) { const node = document.getElementById(id); if (node) dock.append(node); }
  const row = document.querySelector('.chat-input-row'); if (row) dock.append(row);
  const form = document.createElement('form'); form.className = 'editor-request-form'; form.id = 'editor-request-form';
  const prompt = document.createElement('textarea'); prompt.id = 'editor-request'; prompt.rows = 3;
  prompt.placeholder = 'Describe an edit at this time or in the selected region…';
  prompt.setAttribute('aria-label', 'AI edit instruction'); prompt.maxLength = 10000;
  const save = document.createElement('button'); save.className = 'btn btn-primary btn-sm'; save.textContent = 'Save instruction'; save.type = 'submit';
  const saved = document.createElement('span'); saved.id = 'editor-request-status'; saved.setAttribute('role', 'status');
  form.append(prompt, save, saved);
  form.addEventListener('submit', async event => {
    event.preventDefault(); const text = prompt.value.trim(); if (!text) return;
    save.disabled = true;
    try {
      const id = `request-${crypto.randomUUID()}`, region = studio.region;
      await commitStudio([{kind:'annotation', object_id:id, data:{
        tool:region ? 'rectangle' : 'note', text, points:region
          ? [[region.left, region.top], [region.right, region.bottom]] : [[0,0]],
        target_ids:studio.selectedIds, anchor_sec:region?.playhead_sec ?? state.playheadSec ?? 0,
        scope:studio.selectedIds.length ? 'object' : 'frame', coordinate_space:'composition',
      }}], 'AI edit instruction');
      selectMarks([id]); prompt.value = ''; saved.textContent = 'Saved · available to your AI agent';
    } catch (error) { showToast(error.message, 'error'); } finally { save.disabled = false; }
  });
  dock.insertBefore(form, buttons);
  document.getElementById('right-panel').prepend(dock);
  document.getElementById('library-view')?.addEventListener('change', event => {
    document.querySelector(`.tab[data-tab="${event.target.value}"]`)?.click();
  });
  for (const button of document.querySelectorAll('.tab[data-tab]')) button.addEventListener('click', () => {
    document.getElementById('library-view').value = button.dataset.tab;
  });
  function selection() { summary.textContent = `${studio.selectedIds.length} selected · ${studio.selectedMarks.length} marked${studio.region ? ` · region at ${studio.region.playhead_sec.toFixed(2)}s` : ''}${state.reviewOnly ? ' · external MCP available' : ''}`; }
  selection(); window.addEventListener('openedit:studio-selection', selection);
});
