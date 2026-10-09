"""Durable graphics worker entrypoint; stdout contains exactly one JSON result."""
from __future__ import annotations

import argparse
import json
import signal
import sys
from pathlib import Path

from open_edit.integrations.diffusion.graphics import materialize, stop_worker
from open_edit.kernel.render_jobs import RenderJobService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--job-id', required=True)
    args = parser.parse_args()

    def cancelled(signum, frame):
        stop_worker()
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, cancelled)
    signal.signal(signal.SIGINT, cancelled)
    job = RenderJobService().get(args.project, args.job_id)
    try:
        if job is None or job.mode != 'graphics':
            raise ValueError('Graphics job not found')
        print(json.dumps(materialize(args.project, job.params or {})))
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': str(exc)[:500]}))
        sys.exit(1)


if __name__ == '__main__':
    main()
