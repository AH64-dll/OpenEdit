"""Measure targeted agent context and small edits; optional tiktoken instrumentation."""
from __future__ import annotations

import json
import statistics
import tempfile
import time
from pathlib import Path

from open_edit.integrations.diffusion.graphics import DEFAULT_SOURCE
from open_edit.ir.types import AddClipOp
from open_edit.kernel.studio_service import (
    commit_studio,
    get_editing_context,
    save_editing_selection,
)
from open_edit.storage.edit_graph import EditGraphStore


def main():
    try:
        import tiktoken
        tokenizer = tiktoken.get_encoding('cl100k_base')
    except ImportError:
        tokenizer = None

    def measure(value):
        text = json.dumps(value, sort_keys=True)
        return {'bytes': len(text.encode()), 'tokens': len(tokenizer.encode(text)) if tokenizer else None}

    with tempfile.TemporaryDirectory(prefix='openedit-context-benchmark-') as directory:
        root = Path(directory)
        store = EditGraphStore(root / '.open_edit/edit_graph.db')
        store.append_many([AddClipOp(author='user', clip_id='hero' if i == 0 else f'clip-{i}',
                                    asset_hash='a' * 64, track_id='video', position_sec=i * 5,
                                    in_point_sec=2, out_point_sec=7) for i in range(500)])
        source = DEFAULT_SOURCE.replace('return <stage', '// ' + 'Preserve the editable creative direction. ' * 2500 + '\n  return <stage')
        document = {'source': source, 'clip_id': 'graphics-title', 'position_sec': 0}
        commit_studio(root, expected_revision=store.graph_revision(), changes=[
            {'kind': 'document', 'object_id': 'title-doc', 'data': document},
            {'kind': 'annotation', 'object_id': 'placement', 'data': {
                'tool': 'rectangle', 'points': [[10, 20], [30, 40]], 'anchor_sec': 0, 'end_sec': 3,
                'scope': 'range', 'target_ids': ['hero'], 'text': 'Move the title into this region.'}},
        ])
        params = {'selected_ids': ['hero', 'title'], 'annotation_ids': ['placement'],
                  'document_id': 'title-doc', 'playhead_sec': 2}
        durations = []
        for _ in range(5):
            started = time.perf_counter()
            context = get_editing_context(root, **params)
            durations.append(time.perf_counter() - started)
        saves = []
        for _ in range(5):
            started = time.perf_counter()
            save_editing_selection(root, expected_revision=store.graph_revision(), **params)
            saves.append(time.perf_counter() - started)
        old_edit = {'operation': 'apply_studio_changes', 'params': {
            'expected_revision': store.graph_revision(), 'changes': [{'kind': 'document', 'object_id': 'title-doc',
             'data': {**document, 'source': source.replace('Open Edit', 'New title')}}]}}
        small_edit = {'operation': 'apply_graphics_edits', 'params': {
            'expected_revision': store.graph_revision(), 'document_id': 'title-doc',
            'edits': [{'kind': 'text', 'source': 'index.tsx:title', 'text': 'New title'}]}}
        print(json.dumps({'fixture': {'clips': 500, 'graphics_documents': 1, 'source_bytes': len(source.encode()), 'marks': 1},
                          'tokenizer': 'cl100k_base' if tokenizer else None,
                          'context': measure(context), 'whole_document_edit': measure(old_edit),
                          'targeted_edit': measure(small_edit),
                          'context_median_ms': statistics.median(durations) * 1000,
                          'save_focus_median_ms': statistics.median(saves) * 1000}, indent=2))


if __name__ == '__main__':
    main()
