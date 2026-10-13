/* Prioritize the playhead, then fill dirty ranges in the background. */
import { state } from './state.js';

let generation = 0, observed = '', timer, active, seekGeneration = 0, resume = false;
const owner = globalThis.crypto?.randomUUID?.() || String(Math.random()).slice(2);
const node = id => document.querySelector(`#${id}`);
const base = id => `/api/projects/${encodeURIComponent(id)}`;
const checked = chunk => chunk?.playback?.status === 'green' && chunk.playback.current?.url;
const at = (manifest, seconds) => manifest?.chunks?.find(c => seconds >= c.start_sec && seconds < c.end_sec);

export function previewWindow(manifest, seconds) {
  const duration = Number(manifest?.duration_sec || state.currentProjectState?.timeline_full?.duration_sec || state.currentProjectState?.timeline?.total_duration_s || 0);
  const time = Math.max(0, Math.min(Number(seconds) || 0, Math.max(0, duration - .001)));
  const chunks = manifest?.chunks || [], index = chunks.findIndex(c => time >= c.start_sec && time < c.end_sec);
  return index >= 0 ? {start_sec: chunks[Math.max(0, index - 1)].start_sec, end_sec: chunks[Math.min(chunks.length - 1, index + 1)].end_sec}
    : {start_sec: Math.max(0, time - 2), end_sec: Math.min(duration, time + 6)};
}
function status(value, detail = '') {
  const label = node('preview-freshness');
  if (label) { label.dataset.status = value; label.textContent = ({current:'Current', partial:'Ready here · updating timeline', updating:'Updating…', outdated:'Outdated', setup:'Setup needed', empty:'No clips'})[value] || value; label.title = detail; }
}
async function request(id, suffix, body) {
  const response = await fetch(base(id) + suffix, body === undefined ? {} : {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Preview update failed');
  return result;
}
function prioritize(seconds) {
  if (!state.autoPreview || !state.currentProjectId || state.previewChunksEnabled === false) return;
  if (active?.range && seconds >= active.range.start_sec && seconds < active.range.end_sec) return;
  observePreview(true);
}
export function seekChunk(seconds, playing = false) {
  const manifest = state.previewManifest, player = node('preview-player');
  if (!state.previewChunks || !manifest || !player) return false;
  const time = Math.min(Math.max(0, seconds), Math.max(0, manifest.duration_sec - .001));
  const chunk = at(manifest, time);
  const artifact = checked(chunk) ? chunk.playback.current : chunk?.playback?.fallback;
  if (!checked(chunk)) prioritize(time);
  if (!artifact?.url) { resume = playing; status('updating', 'Preparing this range first.'); player.pause(); return true; }
  const localTime = Math.max(0, time - chunk.start_sec);
  state.previewChunkStart = chunk.start_sec; state.previewChunkEnd = chunk.end_sec;
  state.previewRenderId = `chunk:${artifact.artifact_id}`;
  const token = ++seekGeneration;
  const seek = () => {
    if (token !== seekGeneration || !state.previewChunks) return;
    player.currentTime = localTime;
    if (playing) player.play().catch(() => {});
  };
  if (player.getAttribute('src') !== artifact.url) {
    player.addEventListener('loadedmetadata', seek, {once:true}); player.src = artifact.url; player.load();
  } else seek();
  player.style.display = 'block';
  const empty = node('preview-empty'); if (empty) { empty.classList.add('hidden'); empty.style.display = 'none'; }
  player.onerror = () => status('outdated', 'Preview could not load. Refresh preview to retry.');
  const badge = node('preview-mode-badge'); if (badge) badge.textContent = 'Timeline';
  return true;
}
function accept(manifest, revision) {
  if (!manifest?.chunks?.length || manifest.graph_revision !== revision) return false;
  state.previewManifest = manifest; state.previewChunks = true;
  const time = Math.min(state.playheadSec || 0, Math.max(0, manifest.duration_sec - .001));
  const chunk = at(manifest, time), player = node('preview-player');
  if (checked(chunk)) {
    if (player?.getAttribute('src') !== chunk.playback.current.url) seekChunk(time, resume || (player && !player.paused));
    resume = false;
    status(manifest.chunks.every(checked) ? 'current' : 'partial');
  }
  return manifest.chunks.every(checked);
}
async function renderRange(id, revision, token, range) {
  const job = await request(id, '/render', {mode:'preview-chunks', expected_revision:revision, media:'both',
    priority:range ? 'interactive' : 'background', ranges:range ? [range] : [], preview_owner:owner});
  if (token !== generation) { request(id, `/render_jobs/${job.job_id}/cancel`, {}).catch(() => {}); return false; }
  active = {id, job:job.job_id, range};
  let result = job;
  while (['queued', 'running', 'cancelling'].includes(result.status)) {
    await new Promise(resolve => setTimeout(resolve, 500));
    if (token !== generation) return false;
    result = await request(id, `/render_jobs/${job.job_id}`);
    const ready = await request(id, '/preview-chunks');
    if (token !== generation) return false;
    accept(ready.manifest, revision);
  }
  if (token !== generation) return false;
  if (result.status !== 'succeeded') throw new Error(result.error || 'Preview stopped; previous preview kept.');
  const ready = await request(id, '/preview-chunks');
  if (token === generation) accept(ready.manifest, revision);
  active = null;
  return true;
}
async function update(id, revision, token) {
  if (token !== generation) return;
  status('updating');
  try {
    const cached = await request(id, '/preview-chunks');
    if (token !== generation || accept(cached.manifest, revision)) return;
    const range = previewWindow(cached.manifest, state.playheadSec);
    if (range.end_sec <= range.start_sec) return;
    if (!await renderRange(id, revision, token, range)) return;
    if (!state.previewManifest?.chunks.every(checked)) await renderRange(id, revision, token, null);
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
  if (changedProject) { state.previewManifest = null; state.previewChunks = false; resume = false; }
  if (!id || !snapshot?.timeline?.total_duration_s) {
    state.previewManifest = null; state.previewChunks = false;
    const player = node('preview-player'); if (player) { player.pause(); player.removeAttribute('src'); player.load(); }
    status('empty'); return;
  }
  if (!state.capabilities?.timeline) { status('setup', 'Media tools are missing. Open Help for setup.'); return; }
  status('outdated');
  if (state.previewChunksEnabled === false || (!state.autoPreview && !force)) return;
  const token = generation;
  timer = setTimeout(() => update(id, revision, token), force ? 0 : 300);
}
document.addEventListener('DOMContentLoaded', () => {
  window.addEventListener('openedit:snapshot', () => observePreview());
  window.addEventListener('openedit:setup-changed', () => observePreview(true));
  node('preview-player')?.addEventListener('ended', () => {
    if (state.previewChunks && state.previewChunkEnd < state.previewManifest.duration_sec) seekChunk(state.previewChunkEnd, true);
  });
  node('preview-seek')?.addEventListener('input', event => window.dispatchEvent(new CustomEvent('openedit:seek', {detail:Number(event.target.value)})));
});
