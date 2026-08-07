from __future__ import annotations
import json, os, subprocess, time
from pathlib import Path

project = Path('/home/ah64/Videos/video')
cli = Path('/home/ah64/apps/mlt-pipeline/.venv/bin/python')
env = {**os.environ, 'OPEN_EDIT_PREVIEW_CHUNKS': '1', 'OPEN_EDIT_HYPERFRAMES_BIN': '/home/ah64/apps/mlt-pipeline/node_modules/.bin/hyperframes', 'OPEN_EDIT_NODE_BIN': '/usr/bin/node'}
log_dir = project / '.open_edit' / 'benchmark_logs'; log_dir.mkdir(parents=True, exist_ok=True)
for mode in ('proxy', 'final'):
    out = log_dir / f'{mode}.json'
    command = [str(cli), '-m', 'open_edit.cli', 'render', '--mode', mode, '--encoder', 'gpu', '--json', '--force']
    print('START', mode, time.strftime('%Y-%m-%dT%H:%M:%S%z'), flush=True)
    started = time.monotonic()
    proc = subprocess.run(command, cwd=project, env=env, capture_output=True, text=True)
    elapsed = time.monotonic() - started
    record = {'mode': mode, 'returncode': proc.returncode, 'elapsed_sec': elapsed, 'stdout': proc.stdout[-20000:], 'stderr': proc.stderr[-20000:]}
    try:
        record['result'] = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:
        pass
    out.write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps({'mode': mode, 'returncode': proc.returncode, 'elapsed_sec': round(elapsed, 3), 'result_ok': record.get('result', {}).get('ok')}, sort_keys=True), flush=True)
    if proc.returncode != 0:
        break
