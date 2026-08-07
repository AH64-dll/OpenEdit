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
    const d = new Date(iso);
    return d.toLocaleString();
  } catch { return iso; }
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
