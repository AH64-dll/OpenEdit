#!/usr/bin/env python3
"""Provision pinned user-local media/Node runtimes; no admin rights or pip needed."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path


def install_archive(spec: dict, folder: Path, cache: Path) -> Path:
    destination = folder / spec['directory']
    marker = destination / '.openedit-download.sha256'
    if marker.is_file() and marker.read_text().strip() == spec['sha256']:
        return folder / spec['bin']
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / spec['url'].rsplit('/', 1)[-1]
    def digest(path):
        with path.open('rb') as handle:
            return hashlib.file_digest(handle, 'sha256').hexdigest()
    if not archive.is_file() or digest(archive) != spec['sha256']:
        temporary = archive.with_suffix(archive.suffix + '.tmp')
        try:
            with urllib.request.urlopen(spec['url'], timeout=120) as response, temporary.open('wb') as out:
                shutil.copyfileobj(response, out)
            if digest(temporary) != spec['sha256']:
                raise RuntimeError(f"Checksum mismatch: {archive.name}")
            temporary.replace(archive)
        finally:
            temporary.unlink(missing_ok=True)
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=folder) as scratch:
        if archive.suffix == '.zip':
            with zipfile.ZipFile(archive) as package:
                package.extractall(scratch)
        else:
            with tarfile.open(archive) as package:
                package.extractall(scratch, filter='data')
        extracted = Path(scratch) / spec['directory']
        if not extracted.is_dir():
            raise RuntimeError(f"Unexpected layout in {archive.name}")
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(extracted), destination)
    marker.write_text(spec['sha256'] + '\n')
    return folder / spec['bin']


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', type=Path, required=True)
    parser.add_argument('--system-runtime', action='store_true', help='Use existing ffmpeg, ffprobe, melt and Node 24 instead')
    args = parser.parse_args()
    prefix = args.prefix.expanduser().resolve()
    machine = platform.machine().lower()
    if machine not in ('amd64', 'x86_64') or platform.system() not in ('Linux', 'Windows'):
        raise SystemExit('Download releases support Linux x64 and Windows x64. Other platforms can install from source.')
    target = ('windows' if os.name == 'nt' else 'linux') + '-x64'
    manifest = json.loads(Path(__file__).with_name('runtime-downloads.json').read_text())
    paths, env = [], {}
    if not args.system_runtime:
        cache = Path(os.environ.get('OPEN_EDIT_DOWNLOAD_CACHE', str(prefix / '.downloads')))
        node = install_archive(manifest['node'][target], prefix / '.runtime/node', cache)
        media_spec = manifest['media'][target]
        media = install_archive(media_spec, prefix / '.runtime/media', cache)
        paths = [str(node), str(media)]
        if os.name == 'nt':
            env = {'MLT_REPOSITORY': str(prefix / '.runtime/media' / media_spec['repository']),
                   'MLT_DATA': str(media / 'share/mlt'),
                   'MLT_PROFILES_PATH': str(media / 'share/mlt/profiles'),
                   'QT_PLUGIN_PATH': str(prefix / '.runtime/media' / media_spec['qt_plugins'])}
    effective = dict(os.environ)
    effective['PATH'] = os.pathsep.join([*paths, effective.get('PATH', '')])
    effective.update(env)
    for name, flags in [('node', ['--version']), ('npm', ['--version']),
                        ('ffmpeg', ['-version']), ('ffprobe', ['-version']), ('melt', ['-version'])]:
        binary = shutil.which(name, path=effective['PATH'])
        if not binary:
            raise RuntimeError(f'{name} is missing. Setup cannot claim success.')
        result = subprocess.run([binary, *flags], env=effective, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError(f'{name} cannot run: {result.stderr[-800:]}')
        if name == 'node' and int(result.stdout.strip().lstrip('v').split('.')[0]) < 24:
            raise RuntimeError('Node 24 or newer is required')
        print(f'{name}: {(result.stdout or result.stderr).splitlines()[0]}')
    browser = os.environ.get('OPEN_EDIT_CHROMIUM')
    if browser and Path(browser).is_file():
        env['OPEN_EDIT_CHROMIUM'] = str(Path(browser).resolve())
    prefix.mkdir(parents=True, exist_ok=True)
    config = prefix / '.openedit-runtime.json'
    temp = config.with_suffix('.tmp')
    temp.write_text(json.dumps({'version': 1, 'path': paths, 'environment': env}, indent=2))
    temp.replace(config)


if __name__ == '__main__':
    main()
