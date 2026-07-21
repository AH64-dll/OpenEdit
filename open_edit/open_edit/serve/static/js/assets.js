/* ============================================================
   assets.js — left-panel "Assets" tab: list rendering,
   preview modal, and the file-type icon helper. The
   normalizeAssets normalizer lives in state.js so the same
   mapping is used everywhere; this module just consumes it.
   ============================================================ */

import { $, el, fmtDuration, showModal } from './dom.js';

export function assetIcon(a) {
  const fn = (a.filename || '').toLowerCase();
  if (/\.(mp4|mov|avi|mkv|webm)$/.test(fn)) return '🎬';
  if (/\.(mp3|wav|aac|flac|m4a)$/.test(fn)) return '🎵';
  if (/\.(png|jpg|jpeg|gif|webp|bmp)$/.test(fn)) return '🖼️';
  return '📄';
}

export function renderAssets(assets) {
  const list = $('#assets-list');
  if (!list) return;
  list.innerHTML = '';
  if (!assets.length) {
    list.appendChild(el('div', { class: 'empty-state' }, ['No assets yet.', el('br'), 'Upload one below.']));
    return;
  }
  for (const a of assets) {
    const icon = assetIcon(a);
    const card = el('div', { class: 'asset-card' }, [
      el('div', { class: 'asset-icon' }, [icon]),
      el('div', { class: 'asset-meta' }, [
        el('div', { class: 'asset-filename' }, [a.filename]),
        el('div', { class: 'asset-sub' }, [
          `${fmtDuration(a.duration_s)}`,
          a.width && a.height ? ` · ${a.width}×${a.height}` : '',
          a.codec ? ` · ${a.codec}` : '',
          a.has_audio ? ' · audio' : '',
        ].filter(Boolean).join('')),
      ]),
    ]);
    card.addEventListener('click', () => openAssetPreview(a));
    list.appendChild(card);
  }
}

export function openAssetPreview(asset) {
  const titleEl = $('#asset-preview-title');
  const video = $('#asset-preview-video');
  // v1.4 P0-2: the backend's ``AssetInfo.url`` is a servable route
  // (e.g. ``/api/projects/abc/assets/13957.../file``) that streams the
  // asset bytes with the right ``Content-Type`` and Range support.
  // Set it as the ``<video>`` src so the browser actually plays it.
  if (asset.url) {
    video.src = asset.url;
    titleEl.textContent = asset.filename;
  } else {
    // No URL — clear any previous source and annotate the title so
    // the user knows why the player is blank (instead of staring at
    // an empty modal wondering if it's broken). The bare filename
    // alone would be indistinguishable from a working preview that
    // hasn't loaded yet.
    video.removeAttribute('src');
    titleEl.textContent = `${asset.filename} (no preview available)`;
  }
  video.load();
  showModal('modal-asset-preview');
}
