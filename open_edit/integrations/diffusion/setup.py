"""Install the optional compiler worker: python -m ...diffusion.setup."""
from __future__ import annotations

import argparse
import shutil
import subprocess

from open_edit.integrations.diffusion.compiler import worker_directory


def main() -> None:
    parser = argparse.ArgumentParser(description='Install optional pinned Diffusion workers')
    parser.add_argument('--graphics', action='store_true', help='also install the browser graphics worker')
    parser.add_argument('--chromium', action='store_true', help='also download the pinned Chromium browser')
    args = parser.parse_args()
    npm = shutil.which('npm')
    if not npm:
        raise SystemExit('Node.js and npm are required for optional Diffusion authoring')
    subprocess.run(
        [npm, 'ci', '--ignore-scripts', '--no-audit', '--no-fund'],
        cwd=worker_directory(), check=True, timeout=180,
    )
    print('Diffusion authoring worker installed')
    if args.graphics or args.chromium:
        from open_edit.integrations.diffusion.graphics import browser_directory

        directory = browser_directory()
        subprocess.run([npm, 'ci', '--ignore-scripts', '--no-audit', '--no-fund'],
                       cwd=directory, check=True, timeout=180)
        if args.chromium:
            node = shutil.which('node')
            subprocess.run([node, str(directory / 'node_modules/playwright-core/cli.js'), 'install', 'chromium'],
                           cwd=directory, check=True, timeout=300)
        print('Diffusion graphics worker installed')


if __name__ == '__main__':
    main()
