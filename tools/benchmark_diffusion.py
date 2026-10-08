"""Reproducible optional worker benchmark; writes JSON to stdout."""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import tempfile
import time
from pathlib import Path

from open_edit.integrations.diffusion.authoring import get_authoring_view
from open_edit.integrations.diffusion.compiler import parse_and_compile
from open_edit.integrations.diffusion.graphics import (
    DEFAULT_SOURCE,
    get_graphics_view,
    inspect_source,
    materialize,
)
from open_edit.kernel.tool_registry import TOOL_REGISTRY
from open_edit.storage.edit_graph import EditGraphStore


def size(value):
    return len(json.dumps(value, separators=(',', ':')).encode())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--render', action='store_true')
    args = parser.parse_args()
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='openedit-benchmark-') as directory:
        root = Path(directory)
        EditGraphStore(root / '.open_edit/edit_graph.db')
        view = get_authoring_view(root, include_source=True)
        compiler = []
        for _ in range(5):
            before = time.perf_counter()
            parse_and_compile(view['source'])
            compiler.append(time.perf_counter() - before)
        before = time.perf_counter()
        inspect_source(DEFAULT_SOURCE)
        graphics_compile = time.perf_counter() - before
        output = {
            'python': platform.python_version(), 'platform': platform.platform(),
            'node': subprocess.check_output(['node', '--version'], text=True).strip(),
            'empty_project_media_summary_bytes': size(get_authoring_view(root)),
            'empty_project_media_source_bytes': size(view),
            'graphics_summary_bytes': size(get_graphics_view(root)),
            'six_tool_schema_bytes': size({name: model.model_json_schema() for name, model in TOOL_REGISTRY.items()}),
            'compiler_cold_seconds': compiler[0], 'compiler_median_seconds': statistics.median(compiler),
            'graphics_compile_seconds': graphics_compile,
        }
        if args.render:
            params = {'source': DEFAULT_SOURCE, 'duration_sec': 0.5, 'fps': 30}
            before = time.perf_counter()
            rendered = materialize(root, params)
            output['graphics_15_frame_render_seconds'] = time.perf_counter() - before
            before = time.perf_counter()
            cached = materialize(root, params)
            output['graphics_cache_seconds'] = time.perf_counter() - before
            output['cache_hit'] = cached['cache_hit']
            output['browser_version'] = rendered['browser_version']
        try:
            import resource

            rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
            output['peak_child_rss_kib'] = rss / 1024 if platform.system() == 'Darwin' else rss
            output['memory_scope'] = 'Largest terminated child RSS; not aggregate simultaneous process-tree memory'
        except ImportError:
            output['peak_child_rss_kib'] = None
        output['total_seconds'] = time.perf_counter() - started
        print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
