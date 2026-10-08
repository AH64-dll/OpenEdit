/* One project snapshot and selection shared by the studio, inspector and AI. */
import { state } from './state.js';

export const studio = { projectId: null, revision: null, objects: [], selectedIds: [],
  documentId: null, selectedMarks: [], busy: false };
let serial = 0;
const announce = name => {
  state.editingSelection = studio.projectId === state.currentProjectId && Number.isInteger(studio.revision)
    ? { selected_ids: studio.selectedIds, annotation_ids: studio.selectedMarks, document_id: studio.documentId, expected_revision: studio.revision } : null;
  window.dispatchEvent(new CustomEvent(`openedit:studio-${name}`, { detail: studio }));
};
export async function studioRequest(suffix, body, projectId = state.currentProjectId) {
  if (!projectId) throw new Error('Select a project first.');
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}${suffix}`, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) {
    const message = result.detail || result.error || 'Editing request failed';
    const error = new Error(typeof message === 'string' ? message : 'Check the editing values.');
    error.stale = response.status === 409; throw error;
  }
  return result;
}
export async function loadStudio() {
  const projectId = state.currentProjectId, token = ++serial;
  if (!projectId) return;
  const result = await studioRequest('/studio?include_source=true', undefined, projectId);
  if (token !== serial || projectId !== state.currentProjectId) return;
  if (studio.projectId !== projectId) {
    studio.selectedIds = []; studio.selectedMarks = []; studio.documentId = null;
  }
  Object.assign(studio, { projectId, revision: result.graph_revision, objects: result.objects });
  announce('loaded'); return result;
}
export function selectObjects(ids, documentId = studio.documentId) {
  studio.selectedIds = [...new Set(ids)]; studio.documentId = documentId;
  state.selectedIds = studio.selectedIds;
  announce('selection');
}
export function selectMarks(ids) { studio.selectedMarks = [...new Set(ids)]; announce('selection'); }
export function studioObject(kind, id) { return studio.objects.find(o => o.kind === kind && o.object_id === id); }
export async function commitStudio(changes, label, ops = []) {
  if (studio.busy) throw new Error('An edit is being saved.');
  const projectId = state.currentProjectId;
  if (studio.projectId !== projectId || !Number.isInteger(studio.revision)) throw new Error('Reload the project before editing.');
  studio.busy = true; announce('busy');
  try {
    const result = await studioRequest('/studio', { expected_revision: studio.revision, changes, ops, label }, projectId);
    if (projectId === state.currentProjectId) {
      await loadStudio();
      if (result.changed) window.dispatchEvent(new CustomEvent('openedit:graph-changed', { detail: { projectId, studio: true } }));
    }
    return result;
  } finally { studio.busy = false; announce('busy'); }
}
export async function editingContext() {
  return studioRequest('/editing-context', { selected_ids: studio.selectedIds,
    annotation_ids: studio.selectedMarks, playhead_sec: state.playheadSec || 0, document_id: studio.documentId });
}
let selectionTimer;
function publishSelection() {
  clearTimeout(selectionTimer);
  selectionTimer = setTimeout(() => {
    if (studio.projectId !== state.currentProjectId || !Number.isInteger(studio.revision)) return;
    studioRequest('/studio/selection', { expected_revision: studio.revision, selected_ids: studio.selectedIds,
      annotation_ids: studio.selectedMarks, document_id: studio.documentId, playhead_sec: state.playheadSec || 0 }).catch(() => {});
  }, 300);
}
window.addEventListener('openedit:studio-selection', publishSelection);
window.addEventListener('openedit:studio-playhead', publishSelection);
window.addEventListener('openedit:project-selected', () => loadStudio().catch(() => {}));
window.addEventListener('openedit:graph-changed', event => {
  if (!event.detail?.studio && event.detail?.projectId === state.currentProjectId) loadStudio().catch(() => {});
});
window.addEventListener('openedit:snapshot', () => {
  if (studio.projectId !== state.currentProjectId || studio.revision !== state.lastGraphRevision) loadStudio().catch(() => {});
});
