"""Phase 2 (agent B) scratch measurement: review-artifact source-proxy consumption.

Usage: python testrun/phase2_scratch_b/measure.py [--label NAME]
Renders mode=proxy twice (separate workdirs so no render-cache interference),
generating the source proxy in between.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from open_edit.ir.types import AddClipOp, Project
from open_edit.render.orchestrator import render_project
from open_edit.render.source_proxy import generate_asset_proxy
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore

CLIP = REPO / "testrun" / "media" / "take1_intro.mp4"


def build_project(scratch: Path) -> tuple[Path, str]:
    project_dir = scratch / "project"
    open_edit_dir = project_dir / ".open_edit"
    open_edit_dir.mkdir(parents=True, exist_ok=True)
    store = AssetStore(open_edit_dir / "assets")
    assets = store.ingest_paths([str(CLIP)], do_transcribe=False)
    graph = EditGraphStore(open_edit_dir / "edit_graph.db")
    asset = assets[0]
    existing = [op for op in graph.load_all() if op.status == "applied"]
    project = Project(name="phase2_scratch_b", assets={a.asset_hash: a for a in assets})
    if not existing:
        op = AddClipOp(
            author="user",
            asset_hash=asset.asset_hash,
            track_id="v1",
            position_sec=0.0,
            in_point_sec=0.0,
            out_point_sec=asset.duration_sec,
        )
        graph.append(op)
        project.edit_graph.append(op)
    else:
        project.edit_graph = existing
    return project_dir, asset.asset_hash


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="")
    ap.add_argument("--backend", default="cpu", choices=["cpu", "gpu"])
    ap.add_argument("--no-proxy-gen", action="store_true",
                    help="skip generate_asset_proxy (for original-only runs)")
    args = ap.parse_args()

    scratch = REPO / "testrun" / "phase2_scratch_b"
    project_dir, asset_hash = build_project(scratch)
    store = AssetStore(project_dir / ".open_edit" / "assets")

    result: dict = {
        "label": args.label,
        "backend": args.backend,
        "asset_hash": asset_hash,
        "clip": str(CLIP),
        "clip_bytes": CLIP.stat().st_size,
    }

    if not args.no_proxy_gen:
        t0 = time.monotonic()
        proxy = generate_asset_proxy(project_dir, asset_hash)
        result["proxy_gen"] = {
            "status": proxy.status,
            "proxy_hash": proxy.proxy_hash,
            "elapsed_sec": round(proxy.elapsed_sec, 3),
            "output_path": proxy.output_path,
        }
        asset = store.get(asset_hash)
        result["asset_proxy_state"] = {
            "proxy_status": asset.proxy_status if asset else None,
            "proxy_hash": asset.proxy_hash if asset else None,
            "proxy_profile": asset.proxy_profile if asset else None,
        }

    workdir = scratch / f"render-{args.label or 'run'}"
    t0 = time.monotonic()
    rr = render_project(
        "phase2_scratch_b",
        project_dir,
        workdir,
        mode="proxy",
        encoder_backend=args.backend,
    )
    result["render_elapsed_wall"] = round(time.monotonic() - t0, 3)
    result["ok"] = rr.ok
    result["error"] = rr.error
    result["output_path"] = rr.output_path
    result["output_bytes"] = (
        Path(rr.output_path).stat().st_size if rr.ok and rr.output_path else 0
    )
    d = rr.diagnostics or {}
    result["diagnostics"] = {
        "elapsed_sec": d.get("elapsed_sec"),
        "pipe_elapsed_sec": d.get("pipe_elapsed_sec"),
        "emission_profile": d.get("emission_profile"),
        "source_media_policy": d.get("source_media_policy"),
        "source_proxy_hits": d.get("source_proxy_hits"),
        "source_proxy_fallbacks": d.get("source_proxy_fallbacks"),
        "decode_backend": d.get("decode_backend"),
        "stages": {
            k: {"elapsed_sec": v.get("elapsed_sec"), "status": v.get("status"),
                "bytes": v.get("bytes"), "returncode": v.get("returncode")}
            for k, v in (d.get("stages") or {}).items()
        },
    }
    print(json.dumps(result, indent=2, default=str))
    out = scratch / f"measure-{args.label or 'run'}.json"
    out.write_text(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
