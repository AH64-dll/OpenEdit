/* Review, graphics and source share a timeline and an ordinary inspector. */
import { state } from './state.js';
import { $, el, showToast, showModal } from './dom.js';

let history = null, pending = false, fetchId = 0;
export function setWorkspace(view) {
  if (!['review', 'graphics', 'code'].includes(view)) return;
  document.body.dataset.workspace = view;
  for (const button of document.querySelectorAll('.workspace-tab')) {
    const active = button.dataset.workspace === view;
    button.classList.toggle('active', active);
    button.setAttribute('aria-selected', String(active));
    button.tabIndex = active ? 0 : -1;
  }
  $('#authoring-panel').open = view === 'code';
  $('#graphics-panel').open = view === 'graphics';
}

function paintHistory() {
  const available = !!state.currentProjectId && !pending;
  for (const direction of ['undo', 'redo']) {
    const button = $(`#history-${direction}`);
    button.disabled = !available || !history?.[direction];
    button.title = history?.[direction] ? `${direction}: ${history[direction].label}` : `Nothing to ${direction}`;
  }
  const list = $('#history-list');
  list.replaceChildren();
  for (const action of history?.actions || []) {
    const row = el('div', { class: `history-action history-${action.state}` }, [
      el('strong', {}, action.label),
      el('span', { class: 'muted small' }, `${action.author === 'ai' ? 'Agent' : 'You'} · ${action.state === 'undone' ? 'Undone' : action.state === 'abandoned' ? 'Earlier history' : 'Applied'}`),
    ]);
    list.appendChild(row);
  }
  if (!history?.actions?.length) list.appendChild(el('p', { class: 'muted small' }, 'No editing actions yet.'));
}

async function refreshHistory() {
  const id = state.currentProjectId, request = ++fetchId;
  if (!id) { history = null; paintHistory(); return; }
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(id)}/history`);
    if (!response.ok) throw new Error('History unavailable');
    const result = await response.json();
    if (id !== state.currentProjectId || request !== fetchId) return;
    history = result; paintHistory();
  } catch { if (id === state.currentProjectId && request === fetchId) { history = null; paintHistory(); } }
}

async function stepHistory(direction) {
  const id = state.currentProjectId;
  if (!id || pending || !history?.[direction]) return;
  pending = true; paintHistory();
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(id)}/history/${direction}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expected_revision: history.graph_revision }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(response.status === 409 ? 'Project changed. History refreshed; try again.' : result.error || 'History update failed');
    if (id === state.currentProjectId) {
      history = result;
      $('#history-status').textContent = result.changed ? `${direction === 'undo' ? 'Undid' : 'Redid'} ${result.label}` : '';
    }
  } catch (error) { showToast(error.message, 'warn'); }
  finally {
    pending = false;
    paintHistory();
    if (id === state.currentProjectId) {
      window.dispatchEvent(new CustomEvent('openedit:graph-changed', { detail: { projectId: id } }));
      await refreshHistory();
    }
  }
}

async function refreshSetup() {
  const host = $('#setup-checks'); host.textContent = 'Checking…';
  try {
    const response = await fetch('/api/setup');
    if (!response.ok) throw new Error('Setup check unavailable');
    const result = await response.json(); host.replaceChildren();
    state.capabilities = result.capabilities;
    for (const check of result.checks) {
      const row = el('div', { class: 'setup-check' }, [
        el('strong', {}, `${check.ready ? '✓ Ready' : 'Setup needed'} · ${check.name}`),
      ]);
      if (!check.ready) row.appendChild(el('p', { class: 'muted small' }, check.help));
      host.appendChild(row);
    }
    window.dispatchEvent(new CustomEvent('openedit:setup-changed'));
  } catch (error) { host.textContent = error.message; }
}

document.addEventListener('DOMContentLoaded', () => {
  setWorkspace('review');
  for (const button of document.querySelectorAll('.workspace-tab')) {
    button.addEventListener('click', () => setWorkspace(button.dataset.workspace));
    button.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      const tabs = [...document.querySelectorAll('.workspace-tab')];
      const index = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 :
        (tabs.indexOf(button) + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
      event.preventDefault(); setWorkspace(tabs[index].dataset.workspace); tabs[index].focus();
    });
  }
  $('#history-undo').addEventListener('click', () => stepHistory('undo'));
  $('#history-redo').addEventListener('click', () => stepHistory('redo'));
  document.addEventListener('keydown', event => {
    if (!(event.ctrlKey || event.metaKey) || event.altKey ||
        event.target.closest('input, textarea, select, [contenteditable="true"]')) return;
    const key = event.key.toLowerCase();
    if (key === 'z' || key === 'y') { event.preventDefault(); stepHistory(key === 'y' || event.shiftKey ? 'redo' : 'undo'); }
  });
  $('#btn-setup').addEventListener('click', () => { showModal('modal-setup'); refreshSetup(); });
  $('#setup-refresh').addEventListener('click', refreshSetup);
  $('#preview-volume').addEventListener('input', event => { $('#preview-player').volume = Number(event.target.value); });
  $('#preview-fullscreen').addEventListener('click', () => {
    const stage = document.querySelector('#preview-panel');
    if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
    else stage.requestFullscreen?.().catch(() => showToast('Fullscreen unavailable in this browser.', 'info'));
  });
  window.addEventListener('openedit:snapshot', refreshHistory);
  window.addEventListener('openedit:project-selected', () => { history = null; paintHistory(); refreshHistory(); });
  window.addEventListener('openedit:inspect-clip', () => {
    if (window.innerWidth <= 900) $('#right-panel').classList.add('open');
  });
});
