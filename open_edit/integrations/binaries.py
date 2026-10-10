"""Locate runtime binaries (node, npm, melt, Chromium) beyond the process PATH.

Agent hosts launched from a desktop session often start the MCP server
without the user's shell PATH, so nvm/fnm/volta Node and portable MLT builds
are invisible to ``shutil.which``. Resolution order is: explicit override
environment variable, then PATH, then well-known install locations.
``ensure_runtime_path`` prepends the discovered directories to ``PATH`` so
child processes (HyperFrames' ``env node`` shim, render workers) find them too.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

NODE_MIN_MAJOR = 24
MELT_MISSING = ('melt (MLT) not found: every render needs it. Checked OPEN_EDIT_MELT, PATH, '
                '~/.local/share/OpenEdit/runtime and Shotcut installs. Install MLT/Shotcut or set '
                'OPEN_EDIT_MELT; query_project get_readiness shows details.')
_EXE = '.exe' if os.name == 'nt' else ''


@dataclass(frozen=True)
class Resolved:
    """Where a binary was found. ``source`` is 'path', 'env:<VAR>', a manager name, or 'missing'."""

    name: str
    path: str | None
    source: str
    version: str = ''

    @property
    def found(self) -> bool:
        return self.path is not None

    def as_dict(self) -> dict:
        return {'path': self.path, 'source': self.source, 'version': self.version}


@lru_cache(maxsize=32)
def _version(binary: str, mtime: float) -> str:
    try:
        result = subprocess.run([binary, '--version'], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ''
    if result.returncode != 0:
        return ''
    lines = (result.stdout or result.stderr).strip().splitlines()
    return lines[0].strip() if lines else ''


def binary_version(binary: str | None) -> str:
    """First line of ``<binary> --version``; cached until the file changes."""
    if not binary:
        return ''
    try:
        return _version(binary, Path(binary).stat().st_mtime)
    except OSError:
        return ''


def node_major(version: str) -> int | None:
    match = re.match(r'v?(\d+)', version.strip())
    return int(match.group(1)) if match else None


def _home() -> Path:
    return Path(os.environ.get('HOME') or Path.home())


def _version_key(path: Path) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r'\d+', path.name)[:3]) or (0,)


def _node_candidates() -> list[tuple[str, Path]]:
    home = _home()
    found: list[tuple[str, Path]] = []
    nvm_root = Path(os.environ.get('NVM_DIR') or home / '.nvm') / 'versions/node'
    fnm_roots = [Path(os.environ['FNM_DIR'])] if os.environ.get('FNM_DIR') else []
    fnm_roots += [home / '.local/share/fnm', home / '.fnm', home / 'Library/Application Support/fnm']
    managed = [('nvm', nvm_root, 'bin')]
    managed += [('fnm', root / 'node-versions', 'installation/bin') for root in fnm_roots]
    managed += [('asdf', home / '.asdf/installs/nodejs', 'bin')]
    for source, root, sub in managed:
        if root.is_dir():
            for version_dir in sorted(root.iterdir(), key=_version_key, reverse=True):
                found.append((source, version_dir / sub / f'node{_EXE}'))
    found.append(('volta', home / '.volta/bin' / f'node{_EXE}'))
    # install.sh downloads a private Node into <checkout>/.node when none exists.
    checkout = Path(__file__).resolve().parents[2]
    found.append(('open_edit', checkout / '.node/bin' / f'node{_EXE}'))
    return [(source, path) for source, path in found if path.is_file() and os.access(path, os.X_OK)]


def _usable_node(path: str) -> bool:
    major = node_major(binary_version(path))
    return major is not None and major >= NODE_MIN_MAJOR


def resolve_node() -> Resolved:
    """Node >= 24: OPEN_EDIT_NODE_BIN, then PATH, then nvm/fnm/asdf/volta/install.sh Node."""
    override = (os.environ.get('OPEN_EDIT_NODE_BIN') or '').strip()
    if override:
        # An explicit override never silently falls back to another Node.
        path = shutil.which(override)
        return Resolved('node', path, 'env:OPEN_EDIT_NODE_BIN', binary_version(path))
    on_path = shutil.which('node')
    if on_path and _usable_node(on_path):
        return Resolved('node', on_path, 'path', binary_version(on_path))
    for source, candidate in _node_candidates():
        if _usable_node(str(candidate)):
            return Resolved('node', str(candidate), source, binary_version(str(candidate)))
    # Report a too-old Node rather than "missing" so the fix says "upgrade".
    if on_path:
        return Resolved('node', on_path, 'path', binary_version(on_path))
    return Resolved('node', None, 'missing')


def resolve_npm() -> Resolved:
    """npm next to the resolved Node (so both come from the same install)."""
    node = resolve_node()
    if node.path:
        for name in (f'npm{".cmd" if os.name == "nt" else ""}', 'npm'):
            sibling = Path(node.path).with_name(name)
            if sibling.is_file():
                return Resolved('npm', str(sibling), node.source)
    path = shutil.which('npm')
    return Resolved('npm', path, 'path') if path else Resolved('npm', None, 'missing')


def _melt_candidates() -> list[tuple[str, Path]]:
    home = _home()
    runtime = home / '.local/share/OpenEdit/runtime'
    paths = [('open_edit', runtime / 'bin' / f'melt{_EXE}')]
    globs = [
        (runtime, '*Shotcut*/melt'), (runtime, 'Shotcut.app/melt'),
        (home, 'Shotcut*/Shotcut.app/melt'), (home / 'Applications', 'Shotcut*/Shotcut.app/melt'),
        (Path('/opt'), 'shotcut*/Shotcut.app/melt'), (Path('/opt'), 'shotcut*/melt'),
    ]
    if sys.platform == 'darwin':
        paths.append(('shotcut', Path('/Applications/Shotcut.app/Contents/MacOS/melt')))
    if os.name == 'nt':
        program_files = Path(os.environ.get('PROGRAMFILES', r'C:\Program Files'))
        paths.append(('shotcut', program_files / 'Shotcut/melt.exe'))
    for root, pattern in globs:
        if root.is_dir():
            paths += [('shotcut', path) for path in sorted(root.glob(pattern), reverse=True)]
    return [(source, path) for source, path in paths if path.is_file() and os.access(path, os.X_OK)]


def resolve_melt() -> Resolved:
    """melt: OPEN_EDIT_MELT, then PATH, then the OpenEdit runtime dir and Shotcut portable."""
    override = (os.environ.get('OPEN_EDIT_MELT') or '').strip()
    if override:
        # An explicit override never silently falls back to another melt.
        path = shutil.which(override)
        return Resolved('melt', path, 'env:OPEN_EDIT_MELT', binary_version(path))
    path = shutil.which('melt')
    if path:
        return Resolved('melt', path, 'path', binary_version(path))
    for source, candidate in _melt_candidates():
        return Resolved('melt', str(candidate), source, binary_version(str(candidate)))
    return Resolved('melt', None, 'missing')


def melt_bin() -> str | None:
    return resolve_melt().path


def node_bin() -> str | None:
    """Path of a Node >= 24, or None. Callers should report via readiness."""
    node = resolve_node()
    return node.path if node.path and _usable_node(node.path) else None


_SYSTEM_CHROME = (
    '/opt/google/chrome/chrome', '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable',
    '/usr/bin/chromium', '/usr/bin/chromium-browser', '/snap/bin/chromium',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
)


def _playwright_cache() -> Path:
    root = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
    if root:
        return Path(root)
    if sys.platform == 'darwin':
        return _home() / 'Library/Caches/ms-playwright'
    if os.name == 'nt':
        return Path(os.environ.get('LOCALAPPDATA', str(_home() / 'AppData/Local'))) / 'ms-playwright'
    return Path(os.environ.get('XDG_CACHE_HOME', str(_home() / '.cache'))) / 'ms-playwright'


def resolve_chromium() -> Resolved:
    """Browser for Diffusion graphics: OPEN_EDIT_CHROMIUM, then the Playwright cache.

    A system Chrome is reported with source 'system' but is only used once
    the user points OPEN_EDIT_CHROMIUM at it (the browser is part of the
    graphics cache key, so it is never switched silently).
    """
    override = (os.environ.get('OPEN_EDIT_CHROMIUM') or '').strip()
    if override:
        return Resolved('chromium', override if Path(override).is_file() else None, 'env:OPEN_EDIT_CHROMIUM')
    cache = _playwright_cache()
    for name in ('chrome', 'chrome.exe', 'chrome-headless-shell', 'Chromium'):
        for path in sorted(cache.glob(f'chromium*/**/{name}')):
            if path.is_file():
                return Resolved('chromium', str(path), 'playwright')
    for candidate in _SYSTEM_CHROME:
        if Path(candidate).is_file():
            return Resolved('chromium', candidate, 'system')
    return Resolved('chromium', None, 'missing')


def resolve_hyperframes_browser() -> Resolved:
    """Browser HyperFrames will use (its own cache, puppeteer, or an env override)."""
    for var in ('HYPERFRAMES_BROWSER_PATH', 'PRODUCER_HEADLESS_SHELL_PATH'):
        value = (os.environ.get(var) or '').strip()
        if value:
            return Resolved('hyperframes-browser', value if Path(value).is_file() else None, f'env:{var}')
    cache = Path(os.environ.get('XDG_CACHE_HOME', str(_home() / '.cache')))
    for source, root in (('hyperframes', cache / 'hyperframes/chrome'), ('puppeteer', cache / 'puppeteer')):
        if root.is_dir():
            for name in ('chrome-headless-shell', 'chrome', 'chrome.exe', 'Google Chrome for Testing'):
                hits = sorted(root.glob(f'**/{name}'))
                if any(hit.is_file() for hit in hits):
                    return Resolved('hyperframes-browser', str(next(h for h in hits if h.is_file())), source)
    return Resolved('hyperframes-browser', None, 'missing')


_ADDED: list[str] = []


def ensure_runtime_path() -> list[str]:
    """Prepend directories of node/melt found off PATH; returns the directories added.

    Idempotent and safe to call at every entry point. Children inherit the
    updated environment, so HyperFrames' ``#!/usr/bin/env node`` shim and the
    render worker subprocesses resolve the same binaries.
    """
    current = os.environ.get('PATH', '')
    entries = current.split(os.pathsep) if current else []
    added: list[str] = []
    for resolved in (resolve_node(), resolve_melt()):
        if resolved.path and resolved.source != 'path':
            directory = str(Path(resolved.path).parent)
            if directory not in entries and directory not in added:
                added.append(directory)
    if added:
        os.environ['PATH'] = os.pathsep.join([*added, *entries])
        _ADDED.extend(added)
    return added


def runtime_path_additions() -> list[str]:
    """Directories ``ensure_runtime_path`` added in this process (for diagnostics)."""
    return list(_ADDED)
