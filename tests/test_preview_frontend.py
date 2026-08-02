"""Node-sandbox contracts for browser-visible preview diagnostics."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _node_harness import app_js_path, harness, run_node_script


def test_preview_diagnostics_are_exposed_as_safe_structured_labels() -> None:
    script = harness(
        r"""
const formatter = globalThis.OpenEdit?.formatPreviewDiagnostics;
if (typeof formatter !== 'function') {
  throw new Error('formatPreviewDiagnostics is not exposed');
}
const labels = formatter({
  diagnostics: {
    counts: { total_chunks: 4, selected_chunks: 1, skipped_green: 3 },
    selected_ranges: [{ start_sec: 2, end_sec: 3 }],
    elapsed_sec: { video: 1.25, audio: 0.5, mux: 0.25 },
    bytes_written: { video: 100, audio: 20, mux: 120 },
    cache: { hits: 3, misses: 1 },
    evictions: { removed_files: 2, removed_bytes: 200 },
    graph_changed: false,
    partial: true,
    source_path: '/private/should-not-be-visible.mp4',
  },
});
if (labels.counts !== 'Chunks 1/4') throw new Error(labels.counts);
if (labels.skipped_green !== 'Skipped green 3') throw new Error(labels.skipped_green);
if (!labels.ranges.includes('2.00\u20133.00s')) throw new Error(labels.ranges);
if (!labels.elapsed.includes('Video 1.25s')) throw new Error(labels.elapsed);
if (!labels.cache.includes('3 hits / 1 misses')) throw new Error(labels.cache);
if (!labels.evictions.includes('2 files')) throw new Error(labels.evictions);
if (labels.state !== 'Partial') throw new Error(labels.state);
if (JSON.stringify(labels).includes('/private/should-not-be-visible')) {
  throw new Error('diagnostics leaked an absolute source path');
}
console.log(JSON.stringify(labels));
""",
    )
    rc, stdout, stderr = run_node_script(script, app_js_path())
    assert rc == 0, f"rc={rc} stdout={stdout!r} stderr={stderr!r}"
    payload = json.loads(stdout.strip().splitlines()[-1])
    assert payload["state"] == "Partial"
