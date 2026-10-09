/* Full-quality range verification reuses immutable, original-media export jobs. */
import { state } from './state.js';
import './media-marks.js';
import { studio, studioRequest } from './studio-state.js';
const toolbar = document.getElementById('media-mark-toolbar');
const node = (tag, text, attrs = {}) => {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
};
const form = node('form', undefined, {
    id: 'quality-check-form',
    class: 'quality-check-form',
    'aria-label': 'Full-quality range check'
  }),
  start = node('input', undefined, {
    type: 'number',
    min: 0,
    step: 'any',
    value: 0,
    name: 'start_sec',
    'aria-label': 'Range start (seconds)'
  }),
  end = node('input', undefined, {
    type: 'number',
    min: .01,
    step: 'any',
    value: 2,
    name: 'end_sec',
    'aria-label': 'Range end (seconds)'
  });
const button = node('button', 'Check range', {
    type: 'submit',
    class: 'btn btn-secondary btn-xs'
  }),
  cancel = node('button', 'Cancel check', {
    type: 'button',
    class: 'btn btn-secondary btn-xs',
    disabled: ''
  }),
  status = node('span', '', {
    role: 'status',
    id: 'quality-check-status',
    class: 'muted small'
  });
form.append(node('span', 'Full-quality check', {
  class: 'quality-check-label'
}), start, node('span', 'to', {
  class: 'muted quality-check-sep'
}), end, button, cancel, status);
toolbar.append(form);
const dialog = node('dialog', undefined, {
    id: 'quality-check-dialog'
  }),
  close = node('button', 'Close', {
    type: 'button',
    class: 'btn btn-secondary btn-xs'
  }),
  title = node('p'),
  video = node('video', undefined, {
    controls: '',
    playsinline: ''
  });
dialog.append(close, title, video);
document.body.append(dialog);
close.addEventListener('click', () => {
  video.pause();
  dialog.close();
});
dialog.addEventListener('cancel', () => video.pause());
let active = null,
  checking = false,
  accepted = null;
form.addEventListener('submit', async e => {
  e.preventDefault();
  if (checking || !state.currentProjectId) return;
  const project = state.currentProjectId,
    revision = studio.revision;
  checking = true;
  button.disabled = true;
  status.textContent = 'Capturing range…';
  try {
    const job = await studioRequest('/preview/check', {
      expected_revision: revision,
      start_sec: Number(start.value),
      end_sec: Number(end.value)
    }, project);
    active = {
      project,
      id: job.job_id
    };
    cancel.disabled = false;
    let result;
    do {
      await new Promise(resolve => setTimeout(resolve, 750));
      result = await studioRequest(`/render_jobs/${job.job_id}`, undefined, project);
      if (project === state.currentProjectId) status.textContent = `Full-quality check · ${result.status}`;
    } while (['queued', 'running', 'cancelling'].includes(result.status));
    if (project !== state.currentProjectId) return;
    if (result.status !== 'succeeded') throw new Error(result.error || result.status);
    if (revision !== studio.revision) {
      status.textContent = 'Project changed; run the range check again.';
      return;
    }
    if (!result.result?.export_verification?.passed) throw new Error('Range verification failed');
    accepted = {
      project,
      revision
    };
    title.textContent = `Verified full-quality range · revision ${revision} · ${start.value}–${end.value} s`;
    video.src = `/api/projects/${encodeURIComponent(project)}/exports/${job.job_id}/file`;
    video.load();
    status.textContent = 'Full-quality range verified';
    dialog.showModal();
  } catch (error) {
    if (project === state.currentProjectId) status.textContent = error.message;
  } finally {
    active = null;
    checking = false;
    button.disabled = false;
    cancel.disabled = true;
  }
});
cancel.addEventListener('click', async () => {
  if (active) try {
    await studioRequest(`/render_jobs/${active.id}/cancel`, {}, active.project);
  } catch (e) {
    status.textContent = e.message;
  }
});
window.addEventListener('openedit:studio-selection', () => {
  if (checking) return;
  const clips = state.currentProjectState?.timeline_full?.tracks.flatMap(t => t.clips) || [],
    selected = clips.filter(c => studio.selectedIds.includes(c.clip_id));
  if (selected.length) {
    start.value = Math.min(...selected.map(c => c.position_sec));
    end.value = Math.max(...selected.map(c => c.position_sec + c.out_point_sec - c.in_point_sec));
  }
});
window.addEventListener('openedit:studio-loaded', () => {
  if (accepted && accepted.project === state.currentProjectId && accepted.revision !== studio.revision) {
    title.textContent = 'Outdated range check · project changed';
    status.textContent = 'Outdated full-quality range';
  }
});
window.addEventListener('openedit:project-selected', () => {
  accepted = null;
  dialog.close();
  video.pause();
  video.removeAttribute('src');
  start.value = 0;
  end.value = Math.min(2, state.currentProjectState?.timeline_full?.duration_sec || 2);
  status.textContent = '';
});
