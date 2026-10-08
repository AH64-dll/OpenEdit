"""Install the optional compiler worker: python -m ...diffusion.setup."""
from __future__ import annotations

import shutil
import subprocess

from open_edit.integrations.diffusion.compiler import worker_directory


def main() -> None:
    npm = shutil.which('npm')
    if not npm:
        raise SystemExit('Node.js and npm are required for optional Diffusion authoring')
    subprocess.run(
        [npm, 'ci', '--ignore-scripts', '--no-audit', '--no-fund'],
        cwd=worker_directory(), check=True, timeout=180,
    )
    print('Diffusion authoring worker installed')


if __name__ == '__main__':
    main()
