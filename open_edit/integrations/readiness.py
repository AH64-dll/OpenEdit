"""Readiness for user-facing capabilities; never installs or starts a worker."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=32)
def _probe(binary: str, mtime: float, args: tuple[str, ...]) -> str:
    """Bounded checks, refreshed when the executable changes after setup."""
    try:
        result = subprocess.run([binary, *args], capture_output=True, text=True, timeout=3)
        return result.stdout if result.returncode == 0 else ''
    except (OSError, subprocess.SubprocessError):
        return ''


def _output(name: str, *args: str) -> str:
    binary = shutil.which(name)
    if not binary:
        return ''
    try:
        return _probe(binary, Path(binary).stat().st_mtime, args)
    except OSError:
        return ''


def chromium_available() -> bool:
    override = os.environ.get('OPEN_EDIT_CHROMIUM')
    if override:
        return Path(override).is_file()
    root = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
    if root:
        cache = Path(root)
    elif sys.platform == 'darwin':
        cache = Path.home() / 'Library/Caches/ms-playwright'
    elif os.name == 'nt':
        cache = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'ms-playwright'
    else:
        cache = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'ms-playwright'
    return any(p.is_file() for name in ('chrome', 'chrome.exe', 'chrome-headless-shell', 'Chromium')
               for p in cache.glob(f'chromium*/**/{name}'))


def readiness() -> dict:
    from open_edit.integrations.diffusion.compiler import worker_ready
    from open_edit.integrations.diffusion.graphics import graphics_ready
    from open_edit.render.html_overlay import OverlayRenderError, _resolve_hyperframes_bin
    from open_edit.render.mlt_capability import mlt_audio_avfilter_supported, mlt_version

    binaries = {name: bool(shutil.which(name)) for name in ('ffmpeg', 'ffprobe', 'melt', 'node', 'npm')}
    base = binaries['ffmpeg'] and binaries['ffprobe'] and 'libx264' in _output('ffmpeg', '-hide_banner', '-encoders')
    timeline = base and binaries['melt']
    version = _output('node', '--version').strip().lstrip('v').split('.')[0]
    node = binaries['node'] and binaries['npm'] and version.isdigit() and int(version) >= 24
    media = node and worker_ready()
    graphics = base and node and graphics_ready() and chromium_available()
    try:
        html = node and Path(_resolve_hyperframes_bin()).is_file()
    except OverlayRenderError:
        html = False
    legacy = Path(__file__).parent / 'remotion/node_modules/@remotion/cli/package.json'
    mlt = mlt_version()
    return {
        'capabilities': {'timeline': timeline, 'media': media, 'graphics': graphics},
        'checks': [
            {'name': 'Video and audio tools', 'ready': base,
             'help': 'Install a full FFmpeg build including ffprobe and the libx264 encoder.'},
            {'name': 'Timeline preview and export', 'ready': timeline,
             'help': 'Install MLT/melt (Linux: sudo apt install melt; macOS: brew install mlt; Windows: use Shotcut melt or WSL).'},
            {'name': 'Clip properties and source editing', 'ready': media,
             'help': 'Install Node.js 24 and npm, then run: open_edit setup media'},
            {'name': 'Editable graphics', 'ready': graphics,
             'help': 'Install full FFmpeg, Node.js 24 and npm, then run: open_edit setup graphics. Linux may also need Playwright Chromium system libraries.'},
            {'name': 'Advanced HTML package (optional)', 'ready': html,
             'help': 'Only for advanced HTML/CSS/JS overlays: install Node.js 24 and npm, then run open_edit setup html.'},
            {'name': 'Legacy Remotion compatibility (optional)', 'ready': legacy.is_file(),
             'help': 'Only for existing Remotion projects: open_edit setup legacy-remotion'},
            {'name': f"Audio EQ (MLT {'.'.join(map(str, mlt)) if mlt else 'version unknown'})",
             'ready': timeline and mlt_audio_avfilter_supported(),
             'help': 'Audio EQ needs MLT 7.28 or newer (Ubuntu 24.04 ships 7.22); install a newer MLT to render EQ.'},
        ],
    }
