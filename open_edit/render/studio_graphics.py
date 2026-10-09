"""Materialize source-backed clips without replacing their editable documents."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from open_edit.ir.types import Timeline


def graphics_reference_fingerprint(timeline: Timeline) -> str:
    if not timeline.graphics_documents:
        return ''
    from open_edit.integrations.diffusion.graphics import _runtime_digest

    return hashlib.sha256(json.dumps({'documents': timeline.graphics_documents,
                                     'runtime': _runtime_digest()}, sort_keys=True).encode()).hexdigest()


def materialize_graphics_documents(timeline: Timeline, project_path: str | Path) -> Timeline:
    """Bind checked CAS media to a render-local copy; no graph/history mutation."""
    if not any(c.document_id for t in timeline.tracks for c in t.clips):
        return timeline
    from open_edit.integrations.diffusion.graphics import materialize

    result = timeline.model_copy(deep=True)
    rendered = {}
    for track in result.tracks:
        clips = []
        for clip in track.clips:
            if clip.document_id is None or not clip.asset_hash.startswith('studio:'):
                clips.append(clip)
                continue
            document = result.graphics_documents.get(clip.document_id)
            if document is None:
                raise ValueError(f'Missing editable graphics document: {clip.document_id}')
            if not document.get('enabled', True):
                continue
            if clip.document_id not in rendered:
                rendered[clip.document_id] = materialize(project_path, {
                    k: document[k] for k in ('source', 'duration_sec', 'fps')})
            output = rendered[clip.document_id]
            if not output.get('qc_report', {}).get('passed'):
                raise ValueError('Editable graphics output did not pass quality checks')
            clips.append(clip.model_copy(update={'asset_hash': output['asset_hash']}))
        track.clips = clips
    return result
