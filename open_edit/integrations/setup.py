"""Explicit installation of independent optional editing capabilities."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def install(feature: str) -> None:
    if feature in ('media', 'graphics'):
        command = [sys.executable, '-m', 'open_edit.integrations.diffusion.setup']
        if feature == 'graphics':
            command += ['--graphics', '--chromium']
        subprocess.run(command, check=True, timeout=600)
        return
    directory = Path(__file__).parent / ('remotion' if feature == 'legacy-remotion' else 'hyperframes')
    if feature not in ('html', 'legacy-remotion'):
        raise ValueError(f'Unknown optional feature: {feature}')
    from open_edit.integrations.binaries import ensure_runtime_path, node_bin, resolve_npm

    ensure_runtime_path()
    npm = resolve_npm().path if node_bin() else None
    if not npm:
        raise RuntimeError('Install Node.js 24 and npm before setting up this feature '
                           '(checked PATH and nvm/fnm/asdf/volta).')
    subprocess.run([npm, 'ci', '--ignore-scripts', '--no-audit', '--no-fund'], cwd=directory,
                   check=True, timeout=300)
