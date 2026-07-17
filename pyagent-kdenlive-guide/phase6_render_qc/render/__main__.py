"""CLI: ``python3 -m phase6_render_qc.render``."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from phase6_render_qc.render import render as do_render


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--project", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--mode", choices=("proxy", "final"), default="proxy")
    p.add_argument("--in-sec", type=float, default=None)
    p.add_argument("--out-sec", type=float, default=None)
    args = p.parse_args()

    if not Path(args.project).is_file():
        print(json.dumps({"ok": False, "error": f"project not found: {args.project}"}))
        return 1

    rr = do_render(args.project, args.output, mode=args.mode, in_sec=args.in_sec, out_sec=args.out_sec)
    out = {
        "ok": rr.ok,
        "output_path": rr.output_path,
        "mode": rr.mode,
        "profile": rr.profile,
        "duration_sec": rr.duration_sec,
        "elapsed_sec": rr.elapsed_sec,
    }
    if rr.error:
        out["error"] = rr.error
    print(json.dumps(out))
    return 0 if rr.ok else 1


if __name__ == "__main__":
    sys.exit(main())
