#!/usr/bin/env python3
"""Build small download archives from the tested wheel and installer sources."""
from __future__ import annotations

import argparse
import hashlib
import shutil
import tempfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', choices=['linux-x64', 'windows-x64'], required=True)
    parser.add_argument('--dist', type=Path, default=ROOT / 'dist')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/release')
    args = parser.parse_args()
    version = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
    wheel = args.dist / f'open_edit-{version}-py3-none-any.whl'
    if not wheel.is_file():
        raise SystemExit('Build the wheel first: python -m build')
    args.output.mkdir(parents=True, exist_ok=True)
    name = f'OpenEdit-{version}-{args.platform}'
    output = args.output / f'{name}.zip'
    with tempfile.TemporaryDirectory() as directory:
        stage = Path(directory) / name
        (stage / 'wheels').mkdir(parents=True)
        shutil.copy2(wheel, stage / 'wheels' / wheel.name)
        for file in ('install.sh', 'install.ps1', 'LICENSE', 'INSTALL.md'):
            shutil.copy2(ROOT / file, stage / file)
        for folder in ('scripts', 'requirements'):
            shutil.copytree(ROOT / folder, stage / folder, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        (stage / 'README.txt').write_text(
            f'OpenEdit {version} — {args.platform}\n\n'
            + ('Run: powershell -ExecutionPolicy Bypass -File .\\install.ps1\n'
               if args.platform == 'windows-x64' else 'Run: bash ./install.sh\n')
            + 'Read INSTALL.md for prerequisites, verification, agent settings and updates.\n'
              'The installer verifies runtime downloads and a real preview/export before reporting success.\n'
              'No LLM API key is needed for external MCP editing.\n', encoding='utf-8')
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for file in sorted(stage.rglob('*')):
                if file.is_file():
                    archive.write(file, file.relative_to(stage.parent))
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.zip.sha256').write_text(f'{digest}  {output.name}\n')
    print(output)


if __name__ == '__main__':
    main()
