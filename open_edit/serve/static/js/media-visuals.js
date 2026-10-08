/* Filmstrips and wave envelopes decode once per source, outside playback. */
import { state } from './state.js';
const requests = new Map();
const timeline = () => state.currentProjectState?.timeline_full || state.currentProjectState?.timeline || {
  tracks: []
};
const allClips = () => (timeline().tracks || []).flatMap(t => t.clips || []);
let observer;
function getVisuals(project, hash) {
  const key = `${project}:${hash}`;
  if (!requests.has(key)) requests.set(key, fetch(`/api/projects/${encodeURIComponent(project)}/assets/${hash}/visuals`).then(async response => {
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Source visuals unavailable');
    return data;
  }).catch(error => {
    requests.delete(key);
    throw error;
  }));
  return requests.get(key);
}
function paint(el, clip, data) {
  el.querySelector('.clip-source-visual')?.remove();
  const width = Math.min(2048, Math.max(1, Math.round(el.clientWidth))),
    height = 24;
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  canvas.className = 'clip-source-visual';
  canvas.setAttribute('aria-hidden', 'true');
  el.prepend(canvas);
  const ctx = canvas.getContext('2d'),
    duration = clip.out_point_sec - clip.in_point_sec;
  if (clip.track_kind === 'video' && data.thumbnails?.length) {
    const tile = height * 16 / 9;
    for (let x = 0; x < width; x += tile) {
      const time = clip.in_point_sec + (x + tile / 2) / width * duration;
      const thumb = [...data.thumbnails].sort((a, b) => Math.abs(a.time_sec - time) - Math.abs(b.time_sec - time))[0];
      const image = new Image();
      image.onload = () => {
        if (canvas.isConnected) ctx.drawImage(image, x, 0, tile, height);
      };
      image.src = thumb.url;
    }
  } else if (data.waveform?.peaks.length) {
    ctx.fillStyle = '#9fe6c1';
    const {
      peaks,
      step_sec: step
    } = data.waveform;
    for (let x = 0; x < width; x++) {
      const begin = Math.floor((clip.in_point_sec + x / width * duration) / step),
        end = Math.ceil((clip.in_point_sec + (x + 1) / width * duration) / step);
      let peak = 0;
      for (let i = begin; i < Math.max(begin + 1, end); i++) peak = Math.max(peak, peaks[i] || 0);
      const bar = Math.max(1, Math.sqrt(peak) * height);
      ctx.fillRect(x, (height - bar) / 2, 1, bar);
    }
  }
  el.title += ` · cached source ${data.waveform?.peaks.length ? 'waveform' : 'filmstrip'}`;
}
function observe() {
  observer?.disconnect();
  const project = state.currentProjectId;
  observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      observer.unobserve(entry.target);
      const clip = allClips().find(c => c.clip_id === entry.target.dataset.clipId);
      if (!clip || !/^[a-f0-9]{64}$/.test(clip.asset_hash)) continue;
      getVisuals(project, clip.asset_hash).then(data => {
        if (project === state.currentProjectId && entry.target.isConnected) paint(entry.target, clip, data);
      }).catch(error => {
        entry.target.title += ` · ${error.message}`;
      });
    }
  }, {
    root: document.getElementById('timeline-ruler-col'),
    rootMargin: '100px'
  });
  document.querySelectorAll('.timeline-clip').forEach(el => observer.observe(el));
}
window.addEventListener('openedit:timeline-rendered', observe);
window.addEventListener('openedit:project-selected', () => {
  observer?.disconnect();
  requests.clear();
});
