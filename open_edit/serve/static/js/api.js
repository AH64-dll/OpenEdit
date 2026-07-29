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
  async getUiConfig() {
    const r = await fetch('/api/ui-config');
    if (!r.ok) throw await _extractError(r, 'getUiConfig');
    return r.json();
  },

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
    // The ingestion API accepts one canonical repeated ``files`` field.
    for (const f of files) {
      fd.append('files', f, f.name);
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

  async renderProject(id, mode, encoder = 'gpu') {
    const r = await fetch(`/api/projects/${encodeURIComponent(id)}/render`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode, encoder }),
    });
    if (!r.ok) throw await _extractError(r, 'render');
    return r.json();
  },

  async listRenders(id) {
    const r = await fetch(`/api/projects/${encodeURIComponent(id)}/renders`);
    if (!r.ok) {
      throw await _extractError(r, 'listRenders');
    }
    return r.json();
  },

  renderFileUrl(projectId, renderId) {
    return `/api/projects/${encodeURIComponent(projectId)}/renders/${encodeURIComponent(renderId)}/file`;
  },

  async createNote(projectId, { text, t_start, t_end }) {
    const r = await fetch(`/api/projects/${encodeURIComponent(projectId)}/notes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, t_start, t_end }),
    });
    if (!r.ok) throw await _extractError(r, 'createNote');
    return r.json();
  },

  async applyTimelineCommand(id, command, params, expectedRevision) {
    const body = { command, params: params || {}, author: 'user' };
    if (expectedRevision != null) body.expected_revision = expectedRevision;
    const r = await fetch(`/api/projects/${encodeURIComponent(id)}/ops`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw await _extractError(r, 'applyTimelineCommand');
    return r.json();
  },

  thumbnailUrl(id, path) {
    const q = path ? `?path=${encodeURIComponent(path)}` : '';
    return `/api/projects/${encodeURIComponent(id)}/thumbnail${q}`;
  },
};
