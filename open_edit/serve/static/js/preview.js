/* Managed automatic timeline previews reuse the kernel's dirty-range cache. */
import { state } from './state.js';

let generation = 0, observed = '', timer, active, seekGeneration = 0;
const owner = globalThis.crypto?.randomUUID?.() || String(Math.random()).slice(2);
const node = id => document.querySelector(`#${id}`);
const base = id => `/api/projects/${encodeURIComponent(id)}`;
function status(value, detail = '') {
  const label = node('preview-freshness');
  if (label) { label.dataset.status = value; label.textContent = ({ current: 'Current', updating: 'Updating…', outdated: 'Outdated', setup: 'Setup needed', empty: 'No clips' })[value] || value; label.title = detail; }
}
async function request(id, suffix, body) {
  const response = await fetch(base(id) + suffix, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Preview update failed');
  return result;
}

export function seekChunk(seconds, playing = false) {
  const manifest = state.previewManifest, player = node('preview-player');
  if (!state.previewChunks || !manifest || !player) return false;
  const time = Math.min(Math.max(0, seconds), Math.max(0, manifest.duration_sec - .001));
  const chunk = manifest.chunks.find(c => time >= c.start_sec && time < c.end_sec);
  const artifact = chunk?.playback?.status === 'green' ? chunk.playback.current : chunk?.playback?.fallback;
  if (!artifact?.url) { status('outdated', 'This range has no checked preview yet.'); player.pause(); return true; }
  const localTime = Math.max(0, time - chunk.start_sec);
  state.previewChunkStart = chunk.start_sec;
  state.previewChunkEnd = chunk.end_sec;
  state.previewRenderId = `chunk:${artifact.artifact_id}`;
  const seekToken = ++seekGeneration;
  const seek = () => {
    if (seekToken !== seekGeneration || !state.previewChunks) return;
    player.currentTime = localTime;
    if (playing) player.play().catch(() => {});
  };
  if (player.getAttribute('src') !== artifact.url) {
    player.addEventListener('loadedmetadata', seek, { once: true });
    player.src = artifact.url; player.load();
  } else seek();
  player.style.display = 'block';
  const empty = node('preview-empty'); if (empty) { empty.classList.add('hidden'); empty.style.display = 'none'; }
  player.onerror = () => status('outdated', 'Preview could not be loaded. Choose Refresh preview to retry.');
  const badge = node('preview-mode-badge'); if (badge) badge.textContent = 'Timeline';
  return true;
}

function accept(manifest, revision) {
  if (!manifest?.chunks?.length || manifest.graph_revision !== revision) return false;
  if (!manifest.chunks.every(c => c.playback?.status === 'green' && c.playback.current?.url)) return false;
  const player = node('preview-player'), wasPlaying = player && !player.paused;
  state.previewManifest = manifest; state.previewChunks = true;
  seekChunk(state.playheadSec || 0, wasPlaying); status('current');
  return true;
}

async function update(id, revision, token) {
  if (token !== generation) return;
  status('updating');
  try {
    const cached = await request(id, '/preview-chunks');
    if (token !== generation) return;
    if (accept(cached.manifest, revision)) return;
    const job = await request(id, '/render', { mode: 'preview-chunks', expected_revision: revision, media: 'both', priority: 'interactive', ranges: [], preview_owner: owner });
    if (token !== generation) { request(id, `/render_jobs/${job.job_id}/cancel`, {}).catch(() => {}); return; }
    active = { id, job: job.job_id };
    let result = job;
    while (['queued', 'running', 'cancelling'].includes(result.status)) {
      await new Promise(resolve => setTimeout(resolve, 750));
      if (token !== generation) return;
      result = await request(id, `/render_jobs/${job.job_id}`);
    }
    if (token !== generation) return;
    if (result.status !== 'succeeded') throw new Error(result.error || 'Preview update stopped; previous preview kept.');
    const ready = await request(id, '/preview-chunks');
    if (token === generation && !accept(ready.manifest, revision)) status('outdated', 'Some ranges are still waiting for a checked preview.');
  } catch (error) { if (token === generation) status('outdated', error.message); }
  finally { if (token === generation) active = null; }
}

export function observePreview(force = false) {
  const id = state.currentProjectId, snapshot = state.currentProjectState;
  const revision = snapshot?.graph_revision, key = `${id}:${revision}`;
  if (!force && key === observed) return;
  const changedProject = observed.split(':')[0] !== String(id);
  observed = key; generation++; clearTimeout(timer);
  if (active) { request(active.id, `/render_jobs/${active.job}/cancel`, {}).catch(() => {}); active = null; }
  if (changedProject) { state.previewChunks = false; state.previewManifest = null; state.previewChunkStart = 0; }
  if (!id || !snapshot) { status('Select a project'); return; }
  const timeline = snapshot.timeline_full || snapshot.timeline;
  if (!timeline || !(Number(timeline.duration_sec ?? timeline.total_duration_s) > 0)) {
    state.previewChunks = false; state.previewManifest = null; state.previewChunkStart = 0; state.playheadSec = 0;
    const player = node('preview-player'); if (player) { player.pause(); player.removeAttribute('src'); player.load(); }
    status('empty'); return;
  }
  if (!state.capabilities?.timeline) { status('setup', 'Open Setup to enable timeline previews and export.'); return; }
  status('outdated');
  if (state.previewChunksEnabled === false) return;
  if (!state.autoPreview && !force) return;
  const token = generation;
  timer = setTimeout(() => update(id, revision, token), force ? 0 : 1500);
}

document.addEventListener('DOMContentLoaded', () => {
  window.addEventListener('openedit:snapshot', () => observePreview());
  window.addEventListener('openedit:setup-changed', () => observePreview(true));
  node('preview-player')?.addEventListener('ended', () => {
    if (state.previewChunks && state.previewChunkEnd < state.previewManifest.duration_sec) seekChunk(state.previewChunkEnd, true);
  });
  node('preview-seek')?.addEventListener('input', event => window.dispatchEvent(new CustomEvent('openedit:seek', { detail: Number(event.target.value) })));
});
