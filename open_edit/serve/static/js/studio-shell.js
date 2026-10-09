/* Accessible persistent panel sizes and provider-independent AI context. */
import { state } from './state.js';
import { studio, editingContext } from './studio-state.js';
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
  const style = document.createElement('link'); style.rel = 'stylesheet'; style.href = '/studio.css?v=20261008'; document.head.append(style);
  divider(document.getElementById('left-panel'), 'left', '--studio-left', 240, 180, 480);
  divider(document.getElementById('right-panel'), 'right', '--studio-right', 280, 240, 600);
  divider(document.getElementById('timeline-panel'), 'timeline', '--studio-timeline', 190, 120, 500);
  const dock = document.createElement('details'); dock.className = 'studio-ai-dock'; dock.open = true; dock.id = 'studio-ai-dock';
  const heading = document.createElement('summary'); heading.textContent = 'AI editing'; dock.append(heading);
  const hint = document.createElement('p'); hint.className = 'muted small'; hint.textContent = 'Select layers and add marks to direct an edit. External agents can read the same context through MCP.'; dock.append(hint);
  const summary = document.createElement('p'); summary.id = 'studio-ai-selection'; summary.setAttribute('role', 'status'); dock.append(summary);
  const buttons = document.createElement('div'); buttons.className = 'studio-ai-actions';
  const copy = document.createElement('button'); copy.type = 'button'; copy.className = 'btn btn-secondary btn-xs'; copy.textContent = 'Copy AI context'; copy.id = 'studio-copy-context';
  const inspect = document.createElement('button'); inspect.type = 'button'; inspect.className = 'btn btn-ghost btn-xs'; inspect.textContent = 'View context';
  const context = document.createElement('pre'); context.className = 'studio-ai-context'; context.hidden = true;
  const run = async copyText => { try { const result = await editingContext(); const text = JSON.stringify(result, null, 2); context.textContent = text;
    if (copyText) { await navigator.clipboard.writeText(text); showToast('AI context copied.', 'success'); } else context.hidden = !context.hidden;
  } catch (error) { showToast(error.message, 'warn'); } };
  copy.addEventListener('click', () => run(true)); inspect.addEventListener('click', () => run(false)); buttons.append(copy, inspect); dock.append(buttons, context);
  for (const id of ['chat-log', 'chat-status']) { const node = document.getElementById(id); if (node) dock.append(node); }
  const row = document.querySelector('.chat-input-row'); if (row) dock.append(row);
  document.getElementById('right-panel').prepend(dock);
  function selection() { summary.textContent = `${studio.selectedIds.length} selected · ${studio.selectedMarks.length} marked${studio.region ? ` · region at ${studio.region.playhead_sec.toFixed(2)}s` : ''}${state.reviewOnly ? ' · external MCP available' : ''}`; }
  selection(); window.addEventListener('openedit:studio-selection', selection);
});
