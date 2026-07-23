"""Takeover: build ordered, silence-trimmed timeline via the IR API.

No direct DB writes — ops go through EditGraphStore.append(); markers are
NotesStore review notes via add_marker(). Assets in order 1->2->3.
"""
from __future__ import annotations
import re, subprocess
from pathlib import Path

from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.ir.types import AddClipOp, Project
from open_edit.ir.apply import derive_timeline
from open_edit.agent.tools import add_marker

PROJECT_PATH = "/home/ah64/OpenEditProjects/ll"
DB = f"{PROJECT_PATH}/.open_edit/edit_graph.db"
ASSETS_DIR = f"{PROJECT_PATH}/.open_edit/assets"
PROJECT_ID = "ll"

# 1.mp4, 2.mp4, 3.mp4  (timeline order)
ORDER = [
    "f6f74b418b22402f8a4209fa910c35a3010516da91f84180395d9097ae835486",
    "81b7206760911344d456c0e82fc4e2bf16fddcab3f7a0d8ddcb387cb10c908ce",
    "6cc0476493762d1e8f42ca0393bb440bca7bdaf3e3dd1a63be9898cb4b1958ff",
]

SILENCE_NOISE = "-30dB"
SILENCE_D = 0.3
PAD = 0.05
FUMBLE_CUT_SEC = 4.0     # wordless gap >= this -> cut (silent dead air)
FUMBLE_FLAG_SEC = 1.5    # wordless gap >= this -> review marker only
MIN_SEG = 0.1

store = AssetStore(ASSETS_DIR)


def silence_intervals(path: str):
    out = subprocess.run(
        ["ffmpeg", "-i", path, "-af",
         f"silencedetect=noise={SILENCE_NOISE}:d={SILENCE_D}",
         "-f", "null", "-"], capture_output=True, text=True,
    ).stderr
    starts = [float(x) for x in re.findall(r"silence_start:\s*([\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([\d.]+)", out)]
    return sorted((s, e) for s, e in zip(starts, ends))


def compute_keep(asset):
    dur = asset.duration_sec
    path = asset.stored_path
    remove = [(max(0.0, s - PAD), min(dur, e + PAD))
              for (s, e) in silence_intervals(path)]
    review = []
    words = sorted(asset.alignment, key=lambda w: w.t_start)
    prev_end = 0.0
    for w in words:
        gap = w.t_start - prev_end
        if gap >= FUMBLE_CUT_SEC:
            remove.append((prev_end, w.t_start))
        elif gap >= FUMBLE_FLAG_SEC:
            review.append((prev_end, w.t_start, gap))
        prev_end = w.t_end
    tail = dur - prev_end
    if tail >= FUMBLE_CUT_SEC:
        remove.append((prev_end, dur))
    elif tail >= FUMBLE_FLAG_SEC:
        review.append((prev_end, dur, tail))
    # merge
    remove.sort()
    merged = []
    for (s, e) in remove:
        s, e = max(0.0, s), min(dur, e)
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    keep = []
    cur = 0.0
    for (s, e) in merged:
        if s > cur:
            keep.append((cur, s))
        cur = max(cur, e)
    if cur < dur:
        keep.append((cur, dur))
    return keep, review


def local_to_timeline(keep, offset, t):
    acc = 0.0
    for (a, b) in keep:
        if t <= a:
            return offset + acc
        if a <= t <= b:
            return offset + acc + (t - a)
        acc += (b - a)
    return offset + acc


eg = EditGraphStore(DB)
pos = 0.0
total_raw = 0.0
for idx, h in enumerate(ORDER, start=1):
    asset = store.get(h)
    assert asset is not None, h
    total_raw += asset.duration_sec
    keep, review = compute_keep(asset)
    kept_dur = sum(b - a for (a, b) in keep)
    asset_offset = pos
    add_marker({"project_id": PROJECT_ID, "t_start": pos, "t_end": pos,
                "text": f"=== Asset {idx} begins ({h[:8]}, {asset.duration_sec:.1f}s raw, {kept_dur:.1f}s kept) ==="},
               PROJECT_PATH)
    for i, (a, b) in enumerate(keep):
        seg = b - a
        if seg < MIN_SEG:
            continue
        a_r, b_r = round(a, 3), round(b, 3)
        seg = b_r - a_r
        op = AddClipOp(
            asset_hash=h, track_id="v1", track_kind="video",
            position_sec=pos, in_point_sec=a_r,
            out_point_sec=b_r, author="ai",
        )
        eg.append(op)
        pos += seg
    for (gs, ge, gap) in review:
        mp = local_to_timeline(keep, asset_offset, gs)
        add_marker({"project_id": PROJECT_ID, "t_start": mp, "t_end": mp,
                    "text": f"[review] possible fumble in asset {idx} at {gs:.1f}s "
                            f"(wordless {gap:.1f}s, not auto-cut)"},
                   PROJECT_PATH)
    print(f"asset {h[:8]}: raw {asset.duration_sec:.1f}s -> kept {kept_dur:.1f}s "
          f"({len(keep)} segs, {len(review)} fumble flags)")

print(f"\nTOTAL raw {total_raw:.1f}s -> timeline {pos:.1f}s "
      f"(removed {total_raw - pos:.1f}s = {(1 - pos/total_raw)*100:.1f}%)")

# ---- verify ----
ops = eg.load_all()
assets = {h: store.get(h) for h in ORDER}
proj = Project(name="ll", project_id=PROJECT_ID, assets=assets, edit_graph=ops)
tl = derive_timeline(proj)
v1 = next(t for t in tl.tracks if t.track_id == "v1")
clips = sorted(v1.clips, key=lambda c: c.position_sec)
print(f"\nVERIFY: {len(clips)} clips on v1")
for c in clips:
    print(f"  pos={c.position_sec:8.2f} src={c.asset_hash[:8]} "
          f"in={c.in_point_sec:8.2f} out={c.out_point_sec:8.2f} "
          f"dur={c.out_point_sec - c.in_point_sec:7.2f}")
print("first asset:", clips[0].asset_hash[:8], "(expect f6f74b41)")
print("last  asset:", clips[-1].asset_hash[:8], "(expect 6cc04764)")
