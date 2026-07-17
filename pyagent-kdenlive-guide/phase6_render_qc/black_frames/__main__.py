"""CLI: ``python3 -m phase6_render_qc.black_frames``."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from phase6_render_qc.black_frames import list_black_frames


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--video", required=True)
    p.add_argument("--in-sec", type=float, default=0.0)
    p.add_argument("--out-sec", type=float, default=0.0)
    p.add_argument("--threshold", type=float, default=0.10)
    p.add_argument("--min-sec", type=float, default=0.5)
    args = p.parse_args()

    if not Path(args.video).is_file():
        print(json.dumps({"ok": False, "error": f"video not found: {args.video}"}))
        return 1

    r = list_black_frames(args.video, in_sec=args.in_sec, out_sec=args.out_sec,
                          threshold=args.threshold, min_sec=args.min_sec)
    out = {
        "ok": r.ok,
        "in_sec": r.in_sec,
        "out_sec": r.out_sec,
        "threshold": r.threshold,
        "min_sec": r.min_sec,
        "spans": [
            {"start_sec": s.start_sec, "end_sec": s.end_sec, "duration_sec": s.duration_sec}
            for s in r.spans
        ],
        "error": r.error,
    }
    print(json.dumps(out))
    return 0 if r.ok else 1


if __name__ == "__main__":
    sys.exit(main())
