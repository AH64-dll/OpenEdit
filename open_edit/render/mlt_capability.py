"""MLT capability probes: melt version parsing and audio avfilter gating.

MLT before 7.28 silently drops audio ``avfilter.*`` filters such as
``avfilter.equalizer`` (fixed upstream by mltframework/mlt 615aac5). Unknown
versions are treated as supported so a missing or odd melt never raises a
false alarm.
"""
from __future__ import annotations

import functools
import re
import subprocess
from pathlib import Path

from open_edit.ir.types import Timeline

AUDIO_AVFILTER_MIN_VERSION = (7, 28, 0)

_VERSION_RE = re.compile(r'\s*melt\s+(\d+)\.(\d+)(?:\.(\d+))?')


def parse_mlt_version(text: str) -> tuple[int, int, int] | None:
    """Parse the first line of ``melt --version`` (e.g. ``melt 7.41.0``)."""
    lines = text.strip().splitlines()
    match = _VERSION_RE.match(lines[0]) if lines else None
    if match is None:
        return None
    major, minor, patch = match.groups(default='0')
    return int(major), int(minor), int(patch)


@functools.lru_cache(maxsize=8)
def _melt_version_output(binary: str, mtime: float) -> str:
    """Run ``melt --version`` once per executable, refreshed when it changes."""
    try:
        result = subprocess.run([binary, '--version'], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ''
    return result.stdout if result.returncode == 0 else ''


def mlt_version() -> tuple[int, int, int] | None:
    """Installed MLT version from the melt on PATH, or None when unknown."""
    from open_edit.integrations.binaries import melt_bin

    binary = melt_bin()
    if not binary:
        return None
    try:
        mtime = Path(binary).stat().st_mtime
    except OSError:
        return None
    return parse_mlt_version(_melt_version_output(binary, mtime))


def mlt_audio_avfilter_supported() -> bool:
    """True when audio avfilter filters render; unknown versions count as supported."""
    version = mlt_version()
    return version is None or version >= AUDIO_AVFILTER_MIN_VERSION


def _version_text(version: tuple[int, int, int] | None) -> str:
    return '.'.join(map(str, version)) if version else 'unknown'


def _has_enabled_eq(timeline: Timeline) -> bool:
    effects = [e for t in timeline.tracks for e in t.effects]
    effects += [e for t in timeline.tracks for c in t.clips for e in c.effects]
    return any(e.enabled and e.effect_type == 'eq' for e in effects)


def audio_eq_warnings(timeline: Timeline) -> list[str]:
    """Warnings for enabled audio EQ on an MLT that would silently drop it."""
    if mlt_audio_avfilter_supported() or not _has_enabled_eq(timeline):
        return []
    version = _version_text(mlt_version())
    return [
        'Audio EQ needs MLT 7.28 or newer; installed MLT '
        f'{version} will render this clip without EQ.'
    ]
