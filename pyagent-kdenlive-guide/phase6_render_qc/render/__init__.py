"""Render the .kdenlive project to a video file.

Two modes:
- ``proxy``:  640x360 ultrafast encode, for fast iteration (the "open this
  in a normal video player to see what changed" affordance).
- ``final``:  full project profile (resolution, fps, codec from the .kdenlive
  file's own ``<profile>`` element).

Range-limited renders are supported via ``in_sec`` / ``out_sec`` so a
recent change can be checked without re-rendering the whole timeline.

Implementation note: ``melt`` accepts the .kdenlive file directly (its root
element is ``<mlt>``), so no XML extraction is needed. We re-use the same
``nice -n N melt ...`` invocation pattern as ``mlt-pipeline/cmd/render``
rather than introducing a separate render wrapper.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


_NICE_DEFAULT = 10
_PROXY_SIZE = "640x360"
_FINAL_SIZE_FROM_PROFILE = True


@dataclass
class RenderResult:
    ok: bool
    output_path: str
    mode: str
    profile: dict  # parsed <profile> attrs (resolution, fps)
    duration_sec: float
    elapsed_sec: float
    error: Optional[str] = None


def parse_profile(kdenlive_path: str) -> dict:
    """Pull the resolution/fps out of the .kdenlive file's <profile> element.

    Returns an empty dict if no profile is found (caller treats that as a
    fatal config error).
    """
    try:
        text = Path(kdenlive_path).read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return {}
    m = re.search(r'<profile\b([^/>]*)/?>', text)
    if not m:
        return {}
    attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
    return {
        "width": int(attrs.get("width", 0)),
        "height": int(attrs.get("height", 0)),
        "frame_rate_num": int(attrs.get("frame_rate_num", 30)),
        "frame_rate_den": int(attrs.get("frame_rate_den", 1)),
        "description": attrs.get("description", ""),
    }


def parse_project_duration_sec(kdenlive_path: str) -> float:
    """Total timeline duration (seconds) from the project's <tractor out="...">.

    Kdenlive stores ``out`` as a timecode (``HH:MM:SS.mmm``) or a frame
    count; both are converted to seconds. Falls back to 0.0 if the file or
    tractor cannot be read.
    """
    try:
        text = Path(kdenlive_path).read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return 0.0
    m = re.search(r'<tractor\b([^>]*)>', text)
    if not m:
        return 0.0
    attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
    out = attrs.get("out", "0")
    # Timecode form: HH:MM:SS.mmm
    tc = re.match(r"^(\d+):(\d+):(\d+)(?:\.(\d+))?$", out)
    if tc:
        h, mi, s = int(tc.group(1)), int(tc.group(2)), int(tc.group(3))
        frac = int((tc.group(4) or "0").ljust(3, "0")[:3]) / 1000.0
        return round(h * 3600 + mi * 60 + s + frac, 3)
    # Frame-count form.
    try:
        frames = int(out)
    except ValueError:
        return 0.0
    if frames <= 0:
        return 0.0
    profile = parse_profile(kdenlive_path)
    fps = profile.get("frame_rate_num", 30) / max(profile.get("frame_rate_den", 1), 1)
    return round(frames / fps, 3)


def _profile_args(profile: dict) -> list[str]:
    """Render the project's <profile> as melt consumer args.

    Without these, melt's default consumer profile is interlace + weightp,
    which is incompatible with libx264 in many builds and causes the
    encode to stall at the end without flushing the output file.
    """
    if not profile:
        return []
    w = profile.get("width", 0)
    h = profile.get("height", 0)
    fr_n = profile.get("frame_rate_num", 30)
    fr_d = profile.get("frame_rate_den", 1)
    return [
        f"s={w}x{h}",
        f"frame_rate_num={fr_n}",
        f"frame_rate_den={fr_d}",
        "progressive=1",
        "sample_aspect_num=1",
        "sample_aspect_den=1",
        "display_aspect_num=16",
        "display_aspect_den=9",
        "colorspace=709",
    ]


def render(
    kdenlive_path: str,
    output_path: str,
    mode: str = "proxy",
    in_sec: Optional[float] = None,
    out_sec: Optional[float] = None,
    nice_level: int = _NICE_DEFAULT,
) -> RenderResult:
    """Render the project to ``output_path``.

    ``mode`` is "proxy" or "final". ``in_sec``/``out_sec`` are optional
    range limits; if both are set, only that window is rendered.
    """
    if mode not in ("proxy", "final"):
        return RenderResult(False, output_path, mode, {}, 0.0, 0.0, f"invalid mode: {mode}")
    if shutil.which("melt") is None:
        return RenderResult(False, output_path, mode, {}, 0.0, 0.0, "melt not on PATH")

    profile = parse_profile(kdenlive_path)
    if mode == "final" and not profile:
        return RenderResult(False, output_path, mode, {}, 0.0, 0.0, "no <profile> element in project")

    args = [kdenlive_path, "-consumer", f"avformat:{output_path}"]
    if mode == "proxy":
        # Proxy: 640x360, fast. Still pass progressive + framerate + aspect
        # attrs so the consumer profile is valid for libx264.
        args += [
            "s=640x360",
            "frame_rate_num=30",
            "frame_rate_den=1",
            "progressive=1",
            "sample_aspect_num=1",
            "sample_aspect_den=1",
            "display_aspect_num=16",
            "display_aspect_den=9",
            "colorspace=709",
            "vcodec=libx264",
            "acodec=aac",
        ]
    else:
        if profile:
            args += _profile_args(profile)
        args += ["vcodec=libx264", "acodec=aac"]
    if in_sec is not None and out_sec is not None:
        args += ["in=" + str(int(in_sec * profile.get("frame_rate_num", 30))),
                 "out=" + str(int(out_sec * profile.get("frame_rate_num", 30)))]

    if nice_level > 0:
        cmd = ["nice", "-n", str(nice_level), "melt", *args]
    else:
        cmd = ["melt", *args]

    import time
    t0 = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return RenderResult(False, output_path, mode, profile, 0.0, 600.0, "melt timed out after 600s")
    elapsed = time.monotonic() - t0
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip().splitlines()[-1:] or [""]
        return RenderResult(False, output_path, mode, profile, 0.0, elapsed, err[0] or f"melt exited {proc.returncode}")
    if in_sec is not None and out_sec is not None:
        duration = out_sec - in_sec
    else:
        # Full-project render: report the actual timeline length, not 0.0.
        duration = parse_project_duration_sec(kdenlive_path)
    return RenderResult(True, output_path, mode, profile, duration, elapsed, None)
