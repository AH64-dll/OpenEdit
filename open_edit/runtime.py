"""Load the installer-owned runtime beside this virtual environment."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def activate() -> None:
    path = Path(sys.prefix).parent / '.openedit-runtime.json'
    if not path.is_file():
        return
    config = json.loads(path.read_text(encoding='utf-8'))
    if config.get('version') != 1:
        raise RuntimeError('Unsupported OpenEdit runtime configuration; rerun the installer')
    entries = [str(Path(value)) for value in config['path'] if Path(value).is_dir()]
    existing = os.environ.get('PATH', '').split(os.pathsep)
    os.environ['PATH'] = os.pathsep.join(entries + [value for value in existing if value not in entries])
    for name, value in config['environment'].items():
        os.environ.setdefault(name, value)
