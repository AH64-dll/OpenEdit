"""Mirror skills/ into open_edit/harness_skills/ for wheel installs.

Usage: python tools/sync_harness_skills.py [--check]
--check exits 1 and lists differences instead of writing.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'skills'
TARGET = ROOT / 'open_edit' / 'harness_skills'
KEEP = {'__init__.py'}


def tree(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob('*'))
            if p.is_file() and p.name not in KEEP and '__pycache__' not in p.parts}


def main(argv: list[str]) -> int:
    want, have = tree(SOURCE), tree(TARGET)
    drift = sorted(k for k in want.keys() | have.keys() if want.get(k) != have.get(k))
    if '--check' in argv:
        for name in drift:
            print(f'drift: {name}')
        return 1 if drift else 0
    for name in have.keys() - want.keys():
        (TARGET / name).unlink()
    for name, data in want.items():
        path = TARGET / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    for directory in sorted((p for p in TARGET.rglob('*') if p.is_dir()), reverse=True):
        if directory.name != '__pycache__' and not any(directory.iterdir()):
            directory.rmdir()
    shutil.rmtree(TARGET / '__pycache__', ignore_errors=True)
    print(f'synced {len(want)} files, removed {len(have.keys() - want.keys())}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
