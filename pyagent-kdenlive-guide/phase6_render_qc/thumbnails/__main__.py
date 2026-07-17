"""CLI: ``python3 -m phase6_render_qc.thumbnails``.

Two modes (mutually exclusive, picked by flags):
- ``--timestamp-sec T`` → get_thumbnail
- ``--timestamp-sec T --region {x,y,w,h}`` → get_qc_crop
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from phase6_render_qc.thumbnails import get_thumbnail, get_qc_crop


def _result_to_dict(r) -> dict:
    return {
        "ok": r.ok,
        "output_path": r.output_path,
        "width": r.width,
        "height": r.height,
        "file_bytes": r.file_bytes,
        "timestamp_sec": r.timestamp_sec,
        "error": r.error,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--video", required=True)
    p.add_argument("--timestamp-sec", type=float, required=True)
    p.add_argument("--region", default=None, help='JSON: {"x":..,"y":..,"w":..,"h":..}')
    p.add_argument("--output", required=True)
    args = p.parse_args()

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    if args.region:
        try:
            region = json.loads(args.region)
        except json.JSONDecodeError as e:
            print(json.dumps({"ok": False, "error": f"--region must be JSON: {e}"}))
            return 1
        r = get_qc_crop(args.video, args.timestamp_sec, region, args.output)
    else:
        r = get_thumbnail(args.video, args.timestamp_sec, args.output)
    print(json.dumps(_result_to_dict(r)))
    return 0 if r.ok else 1


if __name__ == "__main__":
    sys.exit(main())
