"""Isolated export worker using the durable job's captured source revision."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from open_edit.kernel.export_service import execute_export
from open_edit.kernel.render_jobs import RenderJobService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    try:
        job = RenderJobService().get(args.project, args.job_id)
        if job is None or job.mode != "final" or not (job.params or {}).get("export"):
            raise ValueError("Export job is unavailable")
        result = execute_export(args.project, job.params["export"])
        print(json.dumps(result, allow_nan=False))
        return 0
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
