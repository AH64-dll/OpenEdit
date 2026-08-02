#!/usr/bin/env python3
"""Create disposable render-bench fixtures A/B/C (Phase 1). Does not touch timeline-test edits."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/ah64/OpenEditProjects/render-bench")
MEDIA = ROOT / "media"
PY = Path("/home/ah64/apps/mlt-pipeline/.venv/bin/python")

FOCUS_POPUP_TSX = '''import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

export const FocusPopup: React.FC<{
  titleText: string;
  accent?: string;
}> = ({ titleText, accent = "#5eead4" }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const enter = interpolate(frame, [0, 12], [0, 1], { extrapolateRight: "clamp" });
  const exit = interpolate(
    frame,
    [Math.max(0, durationInFrames - 12), durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const opacity = Math.min(enter, exit);
  const y = interpolate(enter, [0, 1], [24, 0]);
  return (
    <AbsoluteFill style={{ backgroundColor: "transparent" }}>
      <div
        style={{
          position: "absolute",
          left: "10%",
          right: "10%",
          bottom: "12%",
          transform: `translateY(${y}px)`,
          opacity,
          padding: "28px 36px",
          borderRadius: 18,
          backgroundColor: "rgba(8, 12, 18, 0.78)",
          border: `2px solid ${accent}`,
          color: "white",
          fontSize: 54,
          fontFamily: "system-ui, sans-serif",
          boxShadow: "0 18px 48px rgba(0,0,0,0.45)",
        }}
      >
        {titleText}
      </div>
    </AbsoluteFill>
  );
};
'''

ROOT_TSX = '''import React from "react";
import { Composition } from "remotion";
import { TitleCard } from "./compositions/TitleCard";
import { FocusPopup } from "./compositions/FocusPopup";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="TitleCard"
        component={TitleCard}
        durationInFrames={90}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{ titleText: "Open Edit" }}
      />
      <Composition
        id="FocusPopup"
        component={FocusPopup}
        durationInFrames={90}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{ titleText: "Focus", accent: "#5eead4" }}
      />
    </>
  );
};
'''


def run(cmd: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, cwd=str(cwd) if cwd else None)


def init_project(name: str, media: Path) -> Path:
    proj = ROOT / name
    if proj.exists():
        shutil.rmtree(proj)
    proj.mkdir(parents=True)
    # Put only the target media in the folder so init ingests one file.
    linked = proj / media.name
    if not linked.exists():
        linked.symlink_to(media.resolve())
    run([str(PY), "-m", "open_edit.cli", "init", str(proj)])
    return proj


def asset_hash(proj: Path) -> str:
    assets_dir = proj / ".open_edit" / "assets"
    metas = list(assets_dir.glob("*/*.meta.json"))
    if not metas:
        raise SystemExit(f"no assets in {proj}")
    meta = json.loads(metas[0].read_text())
    return meta["asset_hash"]


def append_ops(proj: Path, media_path: Path, *, remotion_specs: list[dict]) -> None:
    sys.path.insert(0, "/home/ah64/apps/mlt-pipeline")
    from open_edit.ir.types import AddClipOp, AddRemotionCompositionOp
    from open_edit.render.remotion_scaffold import (
        ensure_remotion_scaffold,
        write_composition_file,
    )
    from open_edit.storage.edit_graph import EditGraphStore

    h = asset_hash(proj)
    # Probe duration from media via meta
    assets_dir = proj / ".open_edit" / "assets"
    meta = json.loads(next(assets_dir.glob("*/*.meta.json")).read_text())
    duration = float(meta.get("duration_sec") or 60.0)

    store = EditGraphStore(proj / ".open_edit" / "edit_graph.db")
    store.append(
        AddClipOp(
            author="user",
            asset_hash=h,
            track_id="V1",
            track_kind="video",
            position_sec=0.0,
            in_point_sec=0.0,
            out_point_sec=duration,
        )
    )
    if meta.get("has_audio"):
        store.append(
            AddClipOp(
                author="user",
                asset_hash=h,
                track_id="A1",
                track_kind="audio",
                position_sec=0.0,
                in_point_sec=0.0,
                out_point_sec=duration,
            )
        )

    if remotion_specs:
        ensure_remotion_scaffold(proj)
        write_composition_file(
            proj, "src/compositions/FocusPopup.tsx", FOCUS_POPUP_TSX,
        )
        (proj / ".open_edit" / "remotion" / "src" / "Root.tsx").write_text(
            ROOT_TSX, encoding="utf-8",
        )
        remotion_root = proj / ".open_edit" / "remotion"
        if not (remotion_root / "node_modules" / ".bin" / "remotion").exists():
            run(["npm", "install", "--no-fund", "--no-audit"], cwd=remotion_root)
        for spec in remotion_specs:
            store.append(
                AddRemotionCompositionOp(
                    author="user",
                    entry_point="src/index.ts",
                    composition_id=spec["composition_id"],
                    props=spec.get("props") or {},
                    position_sec=float(spec["position_sec"]),
                    duration_sec=float(spec["duration_sec"]),
                    track_id="video_graphics",
                    alpha=bool(spec.get("alpha", False)),
                )
            )


def main() -> int:
    clip60 = MEDIA / "clip60.mp4"
    clip180 = MEDIA / "clip180.mp4"
    if not clip60.is_file() or not clip180.is_file():
        raise SystemExit(f"missing media under {MEDIA}; create clip60/clip180 first")

    # Fixture A: 60s, 1 clip, 0 remotion
    a = init_project("fixture-a", clip60)
    append_ops(a, clip60, remotion_specs=[])

    # Fixture B: 60s, 3 FocusPopup overlays (alpha)
    b = init_project("fixture-b", clip60)
    append_ops(
        b,
        clip60,
        remotion_specs=[
            {
                "composition_id": "FocusPopup",
                "alpha": True,
                "position_sec": 5.0,
                "duration_sec": 3.0,
                "props": {"titleText": "Popup A", "accent": "#5eead4"},
            },
            {
                "composition_id": "FocusPopup",
                "alpha": True,
                "position_sec": 20.0,
                "duration_sec": 3.0,
                "props": {"titleText": "Popup B", "accent": "#fbbf24"},
            },
            {
                "composition_id": "FocusPopup",
                "alpha": True,
                "position_sec": 40.0,
                "duration_sec": 3.0,
                "props": {"titleText": "Popup C", "accent": "#f472b6"},
            },
        ],
    )

    # Fixture C: 180s, 12 Remotion overlays (opaque TitleCard to limit ProRes disk)
    c = init_project("fixture-c", clip180)
    accents = ["#5eead4", "#fbbf24", "#f472b6", "#93c5fd"]
    specs = []
    for i in range(12):
        specs.append(
            {
                "composition_id": "TitleCard",
                "alpha": False,
                "position_sec": 8.0 + i * 13.0,
                "duration_sec": 3.0,
                "props": {"titleText": f"Overlay {i + 1}"},
            }
        )
    # Also register FocusPopup in Root even if unused; TitleCard is enough.
    append_ops(c, clip180, remotion_specs=specs)

    manifest = {
        "root": str(ROOT),
        "fixtures": {
            "A": {"path": str(a), "media": str(clip60), "remotion": 0, "duration_target_s": 60},
            "B": {"path": str(b), "media": str(clip60), "remotion": 3, "duration_target_s": 60, "alpha": True},
            "C": {"path": str(c), "media": str(clip180), "remotion": 12, "duration_target_s": 180, "alpha": False},
        },
        "note": "timeline-test .open_edit was missing; fixtures built from untitled_clean_1.mp4 trims.",
    }
    out = Path("/home/ah64/apps/mlt-pipeline/docs/superpowers/specs/phase1-raw/fixtures.json")
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
