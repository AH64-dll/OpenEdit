/* ============================================================
   api.js — REST client for the Open Edit server. Mirrors the
   route surface in ``open_edit/serve/app.py``. Errors are
   surfaced as ``Error`` instances whose message is the v1.4
   ``{"error": "..."}`` payload (or the legacy ``{"detail": ...}``
   shape) so the rest of the UI can show the actual reason
   rather than just the HTTP status.
   ============================================================ */

// Extract the v1.4 ``{"error": "..."}`` (or legacy ``{"detail": "..."}``)
// from a failed response and surface it in the thrown Error so the rest of
// the UI (toasts / chat log) can show the actual reason rather than just
// the HTTP status. Falls back to the raw text body if the body isn't JSON.
export async function _extractError(r, opName) {
  let msg = '';
  try {
    const body = await r.json();
    if (body && typeof body.error === 'string') msg = body.error;
    else if (body && typeof body.detail === 'string') msg = body.detail;
    else msg = JSON.stringify(body);
  } catch {
    try { msg = await r.text(); } catch { msg = ''; }
  }
  return new Error(msg ? `${opName}: ${msg}` : `${opName}: HTTP ${r.status}`);
}

export const api = {
  async listProjects() {
    const r = await fetch('/api/projects');
    if (!r.ok) throw await _extractError(r, 'listProjects');
    return r.json();
  },

  async createProject(name) {
    const r = await fetch('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    if (!r.ok) throw await _extractError(r, 'createProject');
    return r.json();
  },

  async getProjectState(id) {
    const r = await fetch(`/api/projects/${encodeURIComponent(id)}`);
    if (!r.ok) throw await _extractError(r, 'getProjectState');
    return r.json();
  },

  async ingestFiles(id, files, onProgress) {
    const fd = new FormData();
    // Spec says field name is "files"; backend Prompt-1 uses "file".
    // Send under BOTH names for compatibility.
    for (const f of files) {
      fd.append('files', f, f.name);
      fd.append('file', f, f.name);
    }
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `/api/projects/${encodeURIComponent(id)}/ingest`);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) {
          onProgress(e.loaded / e.total);
        }
      };
      xhr.onload = async () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try { resolve(JSON.parse(xhr.responseText)); }
          catch { resolve({}); }
        } else {
          // Mirror the fetch path: parse the v1.4 ``{"error": "..."}`` body.
          const fakeResp = new Response(xhr.responseText, { status: xhr.status });
          reject(await _extractError(fakeResp, 'ingest'));
        }
      };
      xhr.onerror = () => reject(new Error('ingest: network error'));
      xhr.send(fd);
    });
  },

  async renderProject(id, mode) {
    const r = await fetch(`/api/projects/${encodeURIComponent(id)}/render`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode }),
    });
    if (!r.ok) throw await _extractError(r, 'render');
    return r.json();
  },

  async listRenders(id) {
    const r = await fetch(`/api/projects/${encodeURIComponent(id)}/renders`);
    if (!r.ok) {
      // ``listRenders`` is best-effort: the right panel shows whatever
      // the server has. We don't want a stale render failure to toast
      // repeatedly on every refresh, so swallow with an empty list.
      try {
        const fakeResp = new Response(await r.text(), { status: r.status });
        console.warn('listRenders failed:', (await _extractError(fakeResp, 'listRenders')).message);
      } catch { /* ignore */ }
      return [];
    }
    return r.json();
  },

  thumbnailUrl(id, path) {
    const q = path ? `?path=${encodeURIComponent(path)}` : '';
    return `/api/projects/${encodeURIComponent(id)}/thumbnail${q}`;
  },
};
