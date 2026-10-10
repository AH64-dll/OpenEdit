"""Readiness for user-facing capabilities; never installs or starts a worker.

Each check reports ``ready``, a one-line ``help`` that is the exact next step
when not ready, and a ``detail`` saying what was found (path, version, and
whether it was found off PATH). ``runtime`` lists the resolved binaries.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from open_edit.integrations.binaries import (
    NODE_MIN_MAJOR,
    Resolved,
    node_major,
    resolve_chromium,
    resolve_hyperframes_browser,
    resolve_melt,
    resolve_node,
    resolve_npm,
)

_HW_ENCODERS = ('h264_nvenc', 'hevc_nvenc', 'h264_amf', 'h264_qsv', 'h264_vaapi', 'h264_videotoolbox')


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
    """A browser the Diffusion graphics worker will use without extra configuration."""
    browser = resolve_chromium()
    return browser.found and browser.source != 'system'


def _where(resolved: Resolved) -> str:
    if not resolved.found:
        return f'{resolved.name}: not found'
    version = resolved.version.removeprefix(resolved.name).strip()
    version = f' {version}' if version else ''
    off_path = '' if resolved.source == 'path' else f' (via {resolved.source}; not on PATH, added at startup)'
    return f'{resolved.name}{version} at {resolved.path}{off_path}'


def _melt_install_hint() -> str:
    if sys.platform == 'darwin':
        return 'brew install mlt'
    if os.name == 'nt':
        return 'install Shotcut and set OPEN_EDIT_MELT to its melt.exe'
    return 'sudo apt install melt (or unpack Shotcut portable and set OPEN_EDIT_MELT to Shotcut.app/melt)'


def _node_problem(node: Resolved, npm: Resolved) -> str | None:
    if not node.found:
        return (f'Install Node.js {NODE_MIN_MAJOR}+ (nodejs.org or nvm), or set OPEN_EDIT_NODE_BIN '
                'to its node binary.')
    major = node_major(node.version)
    if major is None or major < NODE_MIN_MAJOR:
        return (f'Node {node.version or "of unknown version"} at {node.path} is too old; install '
                f'Node.js {NODE_MIN_MAJOR}+ or set OPEN_EDIT_NODE_BIN.')
    if not npm.found:
        return f'npm was not found next to {node.path}; reinstall Node.js {NODE_MIN_MAJOR}+ with npm.'
    return None


def _gpu_detail(encoders: str) -> tuple[list[str], str]:
    compiled = [name for name in _HW_ENCODERS if name in encoders]
    nvidia = bool(shutil.which('nvidia-smi'))
    if compiled:
        return compiled, (f'compiled into ffmpeg: {", ".join(compiled)} (each render probes them and '
                          'falls back to libx264; see diagnostics.profile.encoder_vcodec)')
    if nvidia:
        return compiled, ('NVIDIA GPU present but this ffmpeg has no NVENC; renders use CPU libx264. '
                          'Install an NVENC-enabled ffmpeg for faster encodes.')
    return compiled, 'No hardware encoder in ffmpeg; renders use CPU libx264.'


def _ffmpeg_hint() -> str:
    """Point at a libx264-capable ffmpeg outside PATH (common for ~/.local/bin builds)."""
    home = Path(os.environ.get('HOME') or Path.home())
    for candidate in (home / '.local/bin/ffmpeg', Path('/usr/local/bin/ffmpeg'), Path('/opt/homebrew/bin/ffmpeg')):
        if candidate.is_file() and shutil.which('ffmpeg') != str(candidate):
            try:
                encoders = _probe(str(candidate), candidate.stat().st_mtime, ('-hide_banner', '-encoders'))
            except OSError:
                continue
            if 'libx264' in encoders:
                return f' A libx264 ffmpeg exists at {candidate}; put {candidate.parent} first on the MCP server PATH.'
    return ''


def readiness() -> dict:
    from open_edit.integrations.diffusion.compiler import worker_problem
    from open_edit.integrations.diffusion.graphics import graphics_problem
    from open_edit.render.html_overlay import OverlayRenderError, _resolve_hyperframes_bin
    from open_edit.render.mlt_capability import mlt_audio_avfilter_supported, mlt_version

    node, npm, melt = resolve_node(), resolve_npm(), resolve_melt()
    chromium, hf_browser = resolve_chromium(), resolve_hyperframes_browser()
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    encoders = _output('ffmpeg', '-hide_banner', '-encoders')
    base = bool(ffmpeg and ffprobe) and 'libx264' in encoders
    timeline = base and melt.found
    node_problem = _node_problem(node, npm)

    media_problem = node_problem or worker_problem()
    media = base and media_problem is None
    graphics_issue = node_problem or graphics_problem()
    if graphics_issue is None and not chromium_available():
        graphics_issue = (f'A system browser was found at {chromium.path}; set OPEN_EDIT_CHROMIUM to it, '
                          'or run: open_edit setup graphics' if chromium.source == 'system'
                          else 'No Chromium for graphics. Run: open_edit setup graphics')
    graphics = base and graphics_issue is None

    try:
        hf_bin: str | None = _resolve_hyperframes_bin()
        if not Path(hf_bin).is_file() and not shutil.which(hf_bin):
            hf_bin = None
    except OverlayRenderError:
        hf_bin = None
    if node_problem:
        html_issue = node_problem
    elif hf_bin is None:
        html_issue = 'HyperFrames is not installed. Run: open_edit setup html (or npm ci in a source checkout).'
    elif not hf_browser.found:
        html_issue = f'HyperFrames has no browser. Run: {hf_bin} browser ensure'
    else:
        html_issue = None
    html = html_issue is None

    legacy = Path(__file__).parent / 'remotion/node_modules/@remotion/cli/package.json'
    mlt = mlt_version()
    audio_eq = timeline and mlt_audio_avfilter_supported()
    hw_encoders, gpu_detail = _gpu_detail(encoders)
    node_detail = f'{_where(node)}; {_where(npm)}'

    def check(name: str, ready: bool, help_text: str, detail: str) -> dict:
        return {'name': name, 'ready': ready, 'help': help_text, 'detail': detail}

    return {
        'capabilities': {'timeline': timeline, 'media': media, 'graphics': graphics, 'audio_eq': audio_eq},
        'checks': [
            check('Video and audio tools', base,
                  'Install a full FFmpeg build including ffprobe and the libx264 encoder.'
                  + ('' if base else _ffmpeg_hint()),
                  f'ffmpeg: {ffmpeg or "not found"}; ffprobe: {ffprobe or "not found"}; '
                  f'libx264: {"yes" if "libx264" in encoders else "no"}'),
            check('Timeline preview and export', timeline,
                  'Install FFmpeg first.' if not base else f'melt (MLT) is required for every render: {_melt_install_hint()}.',
                  _where(melt)),
            check('Clip properties and source editing', media,
                  media_problem or 'Install a full FFmpeg build first.', node_detail),
            check('Editable graphics', graphics,
                  graphics_issue or 'Install a full FFmpeg build first.',
                  f'{node_detail}; browser: {chromium.path or "not found"} ({chromium.source})'),
            check('Advanced HTML package (optional)', html, html_issue or '',
                  f'hyperframes: {hf_bin or "not found"}; browser: {hf_browser.path or "not found"} ({hf_browser.source})'),
            check('Legacy Remotion compatibility (optional)', legacy.is_file(),
                  'Only for existing Remotion projects: open_edit setup legacy-remotion', ''),
            check(f"Audio EQ (MLT {'.'.join(map(str, mlt)) if mlt else 'version unknown'})", audio_eq,
                  'Audio EQ needs MLT 7.28 or newer (Ubuntu 24.04 ships 7.22); install a newer MLT to render EQ.'
                  if timeline else 'Needs timeline rendering (FFmpeg + melt) first.',
                  _where(melt)),
            check('Hardware video encoding (optional)', bool(hw_encoders),
                  'Optional: install an ffmpeg build with NVENC/QSV/AMF; CPU libx264 works everywhere.',
                  gpu_detail),
        ],
        'runtime': {
            'node': node.as_dict(), 'npm': npm.as_dict(), 'melt': melt.as_dict(),
            'ffmpeg': {'path': ffmpeg, 'source': 'path' if ffmpeg else 'missing', 'version': ''},
            'chromium': chromium.as_dict(), 'hyperframes_browser': hf_browser.as_dict(),
            'hw_encoders': hw_encoders,
        },
    }


def compact_readiness() -> dict:
    """Agent-facing summary: capabilities plus only the checks that need action."""
    result = readiness()
    needs = [{'name': c['name'], 'fix': c['help'], 'found': c['detail']}
             for c in result['checks'] if not c['ready'] and '(optional)' not in c['name']]
    optional = [c['name'] for c in result['checks'] if not c['ready'] and '(optional)' in c['name']]
    return {'capabilities': result['capabilities'], 'needs_setup': needs,
            'optional_unavailable': optional, 'ready': not needs}
