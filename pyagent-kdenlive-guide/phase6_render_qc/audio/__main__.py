"""CLI: ``python3 -m phase6_render_qc.audio [levels|silence]``."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from phase6_render_qc.audio import get_audio_levels, list_silence


def _levels_to_dict(r) -> dict:
    return {
        "ok": r.ok,
        "in_sec": r.in_sec,
        "out_sec": r.out_sec,
        "rms_db": r.rms_db,
        "peak_db": r.peak_db,
        "error": r.error,
    }


def _silence_to_dict(r) -> dict:
    return {
        "ok": r.ok,
        "in_sec": r.in_sec,
        "out_sec": r.out_sec,
        "threshold_db": r.threshold_db,
        "min_sec": r.min_sec,
        "spans": [
            {"start_sec": s.start_sec, "end_sec": s.end_sec, "duration_sec": s.duration_sec}
            for s in r.spans
        ],
        "error": r.error,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("sub", choices=("levels", "silence"))
    p.add_argument("--video", required=True)
    p.add_argument("--in-sec", type=float, default=0.0)
    p.add_argument("--out-sec", type=float, default=0.0)
    p.add_argument("--threshold-db", type=float, default=-35.0)
    p.add_argument("--min-sec", type=float, default=1.0)
    args = p.parse_args()

    if not Path(args.video).is_file():
        print(json.dumps({"ok": False, "error": f"video not found: {args.video}"}))
        return 1

    if args.sub == "levels":
        r = get_audio_levels(args.video, in_sec=args.in_sec, out_sec=args.out_sec)
        print(json.dumps(_levels_to_dict(r)))
        return 0 if r.ok else 1
    r = list_silence(args.video, in_sec=args.in_sec, out_sec=args.out_sec,
                     threshold_db=args.threshold_db, min_sec=args.min_sec)
    print(json.dumps(_silence_to_dict(r)))
    return 0 if r.ok else 1


if __name__ == "__main__":
    sys.exit(main())
