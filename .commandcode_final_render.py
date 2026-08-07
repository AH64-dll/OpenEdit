from __future__ import annotations
import json
import os
import subprocess
import time
from pathlib import Path

p = Path('/home/ah64/Videos/video')
log = p / '.open_edit' / 'benchmark_logs'
log.mkdir(exist_ok=True)
env = {
    **os.environ,
    'OPEN_EDIT_HYPERFRAMES_BIN': '/home/ah64/apps/mlt-pipeline/node_modules/.bin/hyperframes',
    'OPEN_EDIT_NODE_BIN': '/usr/bin/node',
}
cmd = [
    '/home/ah64/apps/mlt-pipeline/.venv/bin/python',
    '-m', 'open_edit.cli',
    'render', '--mode', 'final', '--encoder', 'gpu', '--json', '--force',
]
t0 = time.monotonic()
proc = subprocess.run(cmd, cwd=p, env=env, capture_output=True, text=True)
elapsed = time.monotonic() - t0

so = proc.stdout[-20000:]
se = proc.stderr[-20000:]
rec = {
    'mode': 'final',
    'returncode': proc.returncode,
    'elapsed_sec': elapsed,
    'stdout': so,
    'stderr': se,
}
try:
    rec['result'] = json.loads(proc.stdout.strip().splitlines()[-1])
except Exception:
    pass
(log / 'full_final.json').write_text(json.dumps(rec, indent=2), encoding='utf-8')
print(json.dumps({
    'returncode': proc.returncode,
    'elapsed_sec': round(elapsed, 3),
    'result': rec.get('result', {}),
}, default=str), flush=True)
