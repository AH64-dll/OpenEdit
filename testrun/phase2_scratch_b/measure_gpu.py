"""GPU fastpath comparison: original-only (runtime policy override) vs proxy."""
from __future__ import annotations
import json, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "testrun" / "phase2_scratch_b"))

from measure import build_project  # noqa: E402
from open_edit.render import orchestrator, timeline_plan  # noqa: E402

scratch = REPO / "testrun" / "phase2_scratch_b"
project_dir, asset_hash = build_project(scratch)

def run(label: str, force_original: bool) -> dict:
    if force_original:
        timeline_plan._EMISSION_POLICY["review-artifact"] = "original"
    try:
        t0 = time.monotonic()
        rr = orchestrator.render_project(
            "phase2_scratch_b", project_dir, scratch / f"render-{label}",
            mode="proxy",  # default encoder backend -> gpu
        )
        wall = time.monotonic() - t0
    finally:
        timeline_plan._EMISSION_POLICY["review-artifact"] = "proxy"
    d = rr.diagnostics or {}
    out = {
        "label": label,
        "ok": rr.ok,
        "error": rr.error,
        "wall_sec": round(wall, 3),
        "elapsed_sec": d.get("elapsed_sec"),
        "pipe_elapsed_sec": d.get("pipe_elapsed_sec"),
        "source_media_policy": d.get("source_media_policy"),
        "source_proxy_hits": d.get("source_proxy_hits"),
        "source_proxy_fallbacks": d.get("source_proxy_fallbacks"),
        "cuda_fastpath": d.get("cuda_fastpath"),
        "decode_backend": d.get("decode_backend"),
        "output_bytes": Path(rr.output_path).stat().st_size if rr.ok and rr.output_path else 0,
        "stages": {
            k: {"elapsed_sec": v.get("elapsed_sec"), "status": v.get("status")}
            for k, v in (d.get("stages") or {}).items()
        },
    }
    print(json.dumps(out, indent=2, default=str))
    (scratch / f"gpu-{label}.json").write_text(json.dumps(out, indent=2, default=str))
    return out

print("=== GPU baseline: ORIGINAL-only (policy overridden at runtime) ===")
run("gpu-baseline-original", force_original=True)
print("=== GPU proxy-enabled ===")
run("gpu-proxy-enabled", force_original=False)
