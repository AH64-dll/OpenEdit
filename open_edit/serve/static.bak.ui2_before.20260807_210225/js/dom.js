/* ============================================================
   dom.js — shared DOM helpers used by every UI module. Keeps the
   "create an element / format a number / show a toast" code in
   one place so the other modules don't duplicate it.
   ============================================================ */

export const $ = (sel, root = (typeof document !== 'undefined' ? document : null)) => {
  if (!root) return null;
  return root.querySelector(sel);
};

export const $$ = (sel, root = (typeof document !== 'undefined' ? document : null)) => {
  if (!root) return [];
  return Array.from(root.querySelectorAll(sel));
};

export function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'class') node.className = v;
    else if (k === 'dataset') Object.assign(node.dataset, v);
    else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'html') node.innerHTML = v;
    else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c == null) continue;
    node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  }
  return node;
}

// One restrained icon vocabulary keeps generated controls crisp and aligned.
// Icons are DOM nodes (not glyphs) so they inherit the button's color and
// remain legible across themes, zoom levels, and platform font stacks.
const ICON_PATHS = {
  plus: '<path d="M12 5v14M5 12h14"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14.9-4L3 10m0 0h6M4 13a8 8 0 0 0 14.9 4L21 14m0 0h-6"/>',
  film: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m7 5 2 3m4-3 2 3m-8 8 2 3m4-3 2 3M3 10h18M3 14h18"/>',
  video: '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="m16 10 5-3v10l-5-3z"/>',
  settings: '<path d="M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Z"/><path d="m19.4 15 .1.1a1.4 1.4 0 0 1-2 2l-.1-.1a1.5 1.5 0 0 0-2.5 1v.2a1.4 1.4 0 0 1-2.8 0V18a1.5 1.5 0 0 0-2.5-1l-.1.1a1.4 1.4 0 0 1-2-2l.1-.1a1.5 1.5 0 0 0-1-2.5h-.2a1.4 1.4 0 0 1 0-2.8h.2a1.5 1.5 0 0 0 1-2.5l-.1-.1a1.4 1.4 0 0 1 2-2l.1.1a1.5 1.5 0 0 0 2.5-1v-.2a1.4 1.4 0 0 1 2.8 0v.2a1.5 1.5 0 0 0 2.5 1l.1-.1a1.4 1.4 0 0 1 2 2l-.1.1a1.5 1.5 0 0 0 1 2.5h.2a1.4 1.4 0 0 1 0 2.8h-.2a1.5 1.5 0 0 0-1 2.5Z"/>',
  sun: '<circle cx="12" cy="12" r="3.5"/><path d="M12 2v2.2M12 19.8V22M4.9 4.9l1.6 1.6m10.9 10.9 1.6 1.6M2 12h2.2M19.8 12H22M4.9 19.1l1.6-1.6M17.4 6.5l1.6-1.6"/>',
  moon: '<path d="M20.5 14.2A8.5 8.5 0 0 1 9.8 3.5 8.5 8.5 0 1 0 20.5 14.2Z"/>',
  upload: '<path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M5 14v4h14v-4"/>',
  trash: '<path d="M4 7h16m-10 4v6m4-6v6M9 7V4h6v3m-9 0 1 13h10l1-13"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
  play: '<path d="m9 6 9 6-9 6z"/>',
  pause: '<path d="M8 6v12M16 6v12"/>',
  audio: '<path d="M5 9v6h3l4 3V6L8 9H5Zm11 0a4 4 0 0 1 0 6m2-8a7 7 0 0 1 0 10"/>',
  monitor: '<rect x="3" y="5" width="18" height="13" rx="2"/><path d="M8 21h8m-4-3v3"/>',
  hourglass: '<path d="M7 3h10M7 21h10M8 3c0 4 4 4.5 4 6s-4 2-4 6h8c0-4-4-4.5-4-6s4-2 4-6"/>',
};

export function icon(name, className = 'icon-svg') {
  const svg = el('svg', {
    class: className,
    viewBox: '0 0 24 24',
    'aria-hidden': 'true',
    focusable: 'false',
  });
  svg.innerHTML = ICON_PATHS[name] || ICON_PATHS.monitor;
  return svg;
}

export function showToast(message, kind = '') {
  const t = $('#toast');
  if (!t) return;
  t.textContent = message;
  t.className = 'toast ' + kind;
  setTimeout(() => t.classList.add('hidden'), 3000);
}

export function fmtBytes(n) {
  if (!n && n !== 0) return '—';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
}

export function fmtDuration(s) {
  if (!s || s <= 0) return '0:00';
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, '0')}`;
}

export function fmtTime(iso) {
  if (!iso) return '';
  try {
    // Accept epoch SECONDS (render/note timestamps) or ISO strings.
    let value = iso;
    if (typeof value === 'number' || /^\d{9,10}(\.\d+)?$/.test(String(value).trim())) {
      value = Number(value) * 1000;
    }
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(iso);
    return d.toLocaleString();
  } catch { return String(iso); }
}

export function showModal(id) {
  const node = $('#' + id);
  if (node) node.classList.remove('hidden');
}
export function hideModal(id) {
  const node = $('#' + id);
  if (node) node.classList.add('hidden');
  stopModalMedia(id);
}
export function hideAllModals() {
  $$('.modal').forEach(m => { m.classList.add('hidden'); stopModalMedia(m.id); });
}
export function stopModalMedia(id) {
  if (id) {
    const video = $(`#${id} video`);
    if (video) { video.pause(); video.removeAttribute('src'); video.load(); }
    return;
  }
  $$('.modal video').forEach(v => { v.pause(); v.removeAttribute('src'); v.load(); });
}

export function truncate(s, n) {
  if (!s) return '';
  return s.length <= n ? s : s.slice(0, n - 1) + '…';
}
