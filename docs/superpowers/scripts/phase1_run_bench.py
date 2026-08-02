#!/usr/bin/env python3
"""Phase 1 timed render harness — wraps render_project + QC without editing open_edit/."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, "/home/ah64/apps/mlt-pipeline")

from open_edit.qc.gate import run_qc_gate
from open_edit.render import materialize as materialize_mod
from open_edit.render import orchestrator as orch
from open_edit.render.cache import RenderCache
from open_edit.render.remotion import renderer as remotion_renderer
from open_edit.storage.timeline_cache import derive_or_load_timeline


def disk_snapshot() -> dict[str, Any]:
    usage = shutil.disk_usage("/")
    return {
        "total_gb": round(usage.total / (1024**3), 2),
        "used_gb": round(usage.used / (1024**3), 2),
        "free_gb": round(usage.free / (1024**3), 2),
        "used_pct": round(100.0 * usage.used / usage.total, 1),
    }


def project_disk_bytes(project_dir: Path) -> dict[str, int]:
    def _du(p: Path) -> int:
        if not p.exists():
            return 0
        total = 0
        for root, _dirs, files in os.walk(p):
            for name in files:
                try:
                    total += (Path(root) / name).stat().st_size
                except OSError:
                    pass
        return total

    oe = project_dir / ".open_edit"
    return {
        "project_total": _du(project_dir),
        "assets": _du(oe / "assets"),
        "renders": _du(oe / "renders"),
        "remotion_out": _du(oe / "remotion" / "out"),
        "remotion_node_modules": _du(oe / "remotion" / "node_modules"),
    }


def instrumented_render(
    project_dir: Path,
    *,
    mode: str,
    force: bool,
) -> dict[str, Any]:
    """Call render_project with monkeypatched stage/remotion timers."""
    remotion_events: list[dict[str, Any]] = []
    stage_times: dict[str, float] = {}

    orig_derive = orch.derive_or_load_timeline
    orig_materialize = orch.materialize_remotion_compositions
    orig_render_comp = remotion_renderer.render_composition
    orig_cache_get = RenderCache.get

    def timed_derive(*args, **kwargs):
        t0 = time.monotonic()
        out = orig_derive(*args, **kwargs)
        stage_times["timeline_derive"] = time.monotonic() - t0
        return out

    def timed_materialize(timeline, project_path, **kwargs):
        t0 = time.monotonic()
        out = orig_materialize(timeline, project_path, **kwargs)
        stage_times["remotion_materialize_wrapper"] = time.monotonic() - t0
        return out

    def timed_render_composition(*args, **kwargs):
        t0 = time.monotonic()
        composition_id = kwargs.get("composition_id") or (
            args[2] if len(args) > 2 else "?"
        )
        try:
            result = orig_render_comp(*args, **kwargs)
            remotion_events.append(
                {
                    "event": "render_miss",
                    "composition_id": composition_id,
                    "elapsed_sec": round(time.monotonic() - t0, 3),
                    "output_path": getattr(result, "output_path", None),
                }
            )
            return result
        except Exception as exc:
            remotion_events.append(
                {
                    "event": "render_error",
                    "composition_id": composition_id,
                    "elapsed_sec": round(time.monotonic() - t0, 3),
                    "error": str(exc),
                }
            )
            raise

    def timed_cache_get(self, key, ext="mp4"):
        t0 = time.monotonic()
        path = orig_cache_get(self, key, ext=ext)
        if isinstance(key, str) and key.startswith("materialize:"):
            remotion_events.append(
                {
                    "event": "cache_hit" if path is not None else "cache_miss_lookup",
                    "key": key[:80],
                    "elapsed_sec": round(time.monotonic() - t0, 4),
                    "found": path is not None,
                }
            )
        return path

    orch.derive_or_load_timeline = timed_derive  # type: ignore[assignment]
    orch.materialize_remotion_compositions = timed_materialize  # type: ignore[assignment]
    remotion_renderer.render_composition = timed_render_composition  # type: ignore[assignment]
    materialize_mod.render_composition = timed_render_composition  # type: ignore[assignment]
    RenderCache.get = timed_cache_get  # type: ignore[assignment]

    wall0 = time.monotonic()
    disk_before = disk_snapshot()
    try:
        result = orch.render_project(
            project_id=project_dir.name,
            project_dir=project_dir,
            workdir=project_dir / ".open_edit" / "renders",
            mode=mode,  # type: ignore[arg-type]
            force=force,
        )
    finally:
        orch.derive_or_load_timeline = orig_derive  # type: ignore[assignment]
        orch.materialize_remotion_compositions = orig_materialize  # type: ignore[assignment]
        remotion_renderer.render_composition = orig_render_comp  # type: ignore[assignment]
        materialize_mod.render_composition = orig_render_comp  # type: ignore[assignment]
        RenderCache.get = orig_cache_get  # type: ignore[assignment]

    wall_render = time.monotonic() - wall0
    diagnostics = dict(result.diagnostics or {})

    qc_payload: dict[str, Any] | None = None
    qc_elapsed = 0.0
    if result.ok and result.output_path:
        qc0 = time.monotonic()
        qc = run_qc_gate(
            result.output_path,
            project_dir / ".open_edit" / "thumbs",
            target_duration_s=result.duration_sec,
            mode=mode,
            source_baseline=(diagnostics or {}).get("source_baseline"),
        )
        qc_elapsed = time.monotonic() - qc0
        qc_payload = {
            "passed": qc.passed,
            "elapsed_sec": round(qc_elapsed, 3),
            "checks": [
                {"name": c.name, "passed": c.passed, "detail": c.detail}
                for c in qc.checks
            ],
        }

    wall_total = time.monotonic() - wall0
    stages = diagnostics.get("stages") or {}
    remotion_renders = [e for e in remotion_events if e.get("event") == "render_miss"]
    remotion_hits = [
        e for e in remotion_events
        if e.get("event") == "cache_hit" and e.get("found")
    ]

    return {
        "ok": result.ok,
        "error": result.error,
        "mode": mode,
        "force": force,
        "cache_hit_render": result.cache_hit,
        "output_path": result.output_path,
        "duration_sec": result.duration_sec,
        "edit_graph_hash": result.edit_graph_hash,
        "wall_clock_sec": round(wall_total, 3),
        "wall_render_only_sec": round(wall_render, 3),
        "orchestrator_elapsed_sec": result.elapsed_sec,
        "stage_breakdown_sec": {
            "timeline_derive": round(stage_times.get("timeline_derive", 0.0), 3),
            "remotion_materialize": round(
                (stages.get("remotion_materialize") or {}).get("elapsed_sec", 0.0), 3
            ),
            "remotion_materialize_wrapper": round(
                stage_times.get("remotion_materialize_wrapper", 0.0), 3
            ),
            "melt": round((stages.get("melt") or {}).get("elapsed_sec", 0.0), 3),
            "ffmpeg": round((stages.get("ffmpeg") or {}).get("elapsed_sec", 0.0), 3),
            "audio_melt": round((stages.get("audio") or {}).get("elapsed_sec", 0.0), 3),
            "source_repair": round(
                ((diagnostics.get("repair") or {}).get("elapsed_sec") or 0.0), 3
            ),
            "qc": round(qc_elapsed, 3),
        },
        "remotion": {
            "composition_count_events_render": len(remotion_renders),
            "composition_cache_hits": len(remotion_hits),
            "render_wall_sum_sec": round(
                sum(e.get("elapsed_sec", 0.0) for e in remotion_renders), 3
            ),
            "events": remotion_events,
        },
        "repair": diagnostics.get("repair"),
        "profile": diagnostics.get("profile") or result.profile,
        "qc": qc_payload,
        "disk_before": disk_before,
        "disk_after": disk_snapshot(),
        "project_bytes": project_disk_bytes(project_dir),
        "diagnostics_raw_stages": stages,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("fixture", choices=["A", "B", "C", "a", "b", "c"])
    ap.add_argument("--mode", choices=["proxy", "final"], required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--label", default="")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    fixtures = json.loads(
        Path(
            "/home/ah64/apps/mlt-pipeline/docs/superpowers/specs/phase1-raw/fixtures.json"
        ).read_text()
    )
    key = args.fixture.upper()
    project_dir = Path(fixtures["fixtures"][key]["path"])
    label = args.label or f"{key}_{args.mode}_{'force' if args.force else 'cache'}"

    print(f"=== RUN {label} project={project_dir} ===", flush=True)
    print(f"disk_before={disk_snapshot()}", flush=True)
    payload = instrumented_render(project_dir, mode=args.mode, force=args.force)
    payload["label"] = label
    payload["fixture"] = key
    payload["commands"] = [
        f"{sys.executable} {Path(__file__).name} {key} --mode {args.mode}"
        + (" --force" if args.force else "")
        + f" --out {args.out}"
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({
        "label": label,
        "ok": payload["ok"],
        "wall_clock_sec": payload["wall_clock_sec"],
        "cache_hit_render": payload["cache_hit_render"],
        "stages": payload["stage_breakdown_sec"],
        "remotion_render_sum": payload["remotion"]["render_wall_sum_sec"],
        "remotion_cache_hits": payload["remotion"]["composition_cache_hits"],
        "error": payload.get("error"),
        "disk_after": payload["disk_after"],
    }, indent=2), flush=True)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
