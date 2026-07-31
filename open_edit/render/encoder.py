"""Video encoder backend selection: GPU (default) or CPU.

Resolves the best available hardware encoder at runtime and exposes a
stable API for melt consumers and ffmpeg overlay passes.

``select_encoder`` is the single source for per-encoder quality args:
one policy, rendered in both arg dialects (melt ``key=value`` consumer
args and ffmpeg flags). ``profiles`` consumes ``EncoderSpec.melt_args``
and ``graphics_overlay`` consumes ``EncoderSpec.ffmpeg_args``.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Literal

EncoderBackend = Literal["gpu", "cpu"]

# GPU encoders probed in preference order when backend=gpu.
_GPU_ORDER: tuple[str, ...] = ("h264_nvenc", "h264_amf", "h264_qsv", "h264_vaapi")


@dataclass(frozen=True)
class EncoderSpec:
    """Quality args for one encoder, rendered in both arg dialects.

    ``melt_args`` are ``key=value`` consumer args; ``ffmpeg_args`` are
    ffmpeg flags (without ``-c:v``). Each dialect keeps its own value
    spellings for the same policy (e.g. melt ``b=10M`` vs ffmpeg
    ``-b:v 10M``, melt proxy ``cq=23`` vs ffmpeg preview ``-cq 20``).
    """
    vcodec: str
    melt_args: tuple[str, ...]
    ffmpeg_args: tuple[str, ...]


# key: (vcodec, final) -> EncoderSpec. final=True is the deliverable
# render; final=False is the fast proxy/preview pass.
_SPECS: dict[tuple[str, bool], EncoderSpec] = {
    ("h264_nvenc", False): EncoderSpec(
        "h264_nvenc",
        melt_args=("rc=constqp", "cq=23", "preset=p4"),
        ffmpeg_args=("-preset", "p4", "-rc", "constqp", "-cq", "20", "-profile:v", "high"),
    ),
    ("h264_nvenc", True): EncoderSpec(
        "h264_nvenc",
        melt_args=("rc=vbr", "b=10M", "maxrate=14M", "bufsize=20M", "preset=p5", "bf=2"),
        ffmpeg_args=(
            "-preset", "p5",
            "-rc", "vbr",
            "-b:v", "10M",
            "-maxrate", "14M",
            "-bufsize", "20M",
            "-profile:v", "high",
            "-bf", "2",
        ),
    ),
    ("h264_amf", False): EncoderSpec(
        "h264_amf",
        melt_args=(),
        ffmpeg_args=("-quality", "balanced", "-rc", "cqp", "-qp_i", "20", "-qp_p", "20"),
    ),
    ("h264_amf", True): EncoderSpec(
        "h264_amf",
        melt_args=("quality=quality", "rc=vbr_peak", "b=10M", "maxrate=14M"),
        ffmpeg_args=("-quality", "quality", "-rc", "vbr_peak", "-b:v", "10M", "-maxrate", "14M"),
    ),
    ("h264_qsv", False): EncoderSpec(
        "h264_qsv",
        melt_args=(),
        ffmpeg_args=("-preset", "medium", "-global_quality", "20"),
    ),
    ("h264_qsv", True): EncoderSpec(
        "h264_qsv",
        melt_args=("global_quality=18", "preset=medium"),
        ffmpeg_args=("-preset", "medium", "-global_quality", "18"),
    ),
    ("h264_vaapi", False): EncoderSpec(
        "h264_vaapi",
        melt_args=(),
        ffmpeg_args=("-qp", "20"),
    ),
    ("h264_vaapi", True): EncoderSpec(
        "h264_vaapi",
        melt_args=("crf=18",),
        ffmpeg_args=("-qp", "18"),
    ),
    ("libx264", False): EncoderSpec(
        "libx264",
        melt_args=("crf=23", "preset=veryfast"),
        ffmpeg_args=("-preset", "veryfast", "-crf", "20"),
    ),
    ("libx264", True): EncoderSpec(
        "libx264",
        melt_args=("crf=18", "preset=medium", "vb=0", "profile=high"),
        ffmpeg_args=("-preset", "medium", "-crf", "18", "-profile:v", "high"),
    ),
}

TIERS: tuple[str, ...] = ("fast", "standard", "high", "archival")

# (family, tier) -> (melt args, ffmpeg args)
# fast == legacy proxy policy; standard == legacy final policy (bit-identical).
# hevc/av1 use the same policy scaled for their efficiency (crf-equivalent +6/+8,
# bitrate x1.2); CPU rows use crf+preset.
_POLICY: dict[tuple[str, str], tuple[tuple[str, ...], tuple[str, ...]]] = {
    ("h264", "fast"): (
        ("rc=constqp", "cq=23", "preset=p4"),
        ("-preset", "p4", "-rc", "constqp", "-cq", "20", "-profile:v", "high"),
    ),
    ("h264", "standard"): (
        ("rc=vbr", "b=10M", "maxrate=14M", "bufsize=20M", "preset=p5", "bf=2"),
        ("-preset", "p5", "-rc", "vbr", "-b:v", "10M", "-maxrate", "14M",
         "-bufsize", "20M", "-profile:v", "high", "-bf", "2"),
    ),
    ("h264", "high"): (
        ("rc=vbr", "b=18M", "maxrate=24M", "bufsize=28M", "preset=p6", "bf=2"),
        ("-preset", "p6", "-rc", "vbr", "-b:v", "18M", "-maxrate", "24M",
         "-bufsize", "28M", "-profile:v", "high", "-bf", "2"),
    ),
    ("h264", "archival"): (
        ("rc=vbr", "b=25M", "maxrate=32M", "bufsize=40M", "preset=p6", "bf=2"),
        ("-preset", "p6", "-rc", "vbr", "-b:v", "25M", "-maxrate", "32M",
         "-bufsize", "40M", "-profile:v", "high", "-bf", "2"),
    ),
    ("hevc", "fast"): (
        ("rc=constqp", "cq=26", "preset=p4"),
        ("-preset", "p4", "-rc", "constqp", "-cq", "23", "-profile:v", "main"),
    ),
    ("hevc", "standard"): (
        ("rc=vbr", "b=12M", "maxrate=16M", "bufsize=24M", "preset=p5"),
        ("-preset", "p5", "-rc", "vbr", "-b:v", "12M", "-maxrate", "16M",
         "-bufsize", "24M", "-profile:v", "main"),
    ),
    ("hevc", "high"): (
        ("rc=vbr", "b=22M", "maxrate=28M", "bufsize=34M", "preset=p6"),
        ("-preset", "p6", "-rc", "vbr", "-b:v", "22M", "-maxrate", "28M",
         "-bufsize", "34M", "-profile:v", "main"),
    ),
    ("hevc", "archival"): (
        ("rc=vbr", "b=30M", "maxrate=38M", "bufsize=46M", "preset=p6"),
        ("-preset", "p6", "-rc", "vbr", "-b:v", "30M", "-maxrate", "38M",
         "-bufsize", "46M", "-profile:v", "main"),
    ),
    ("av1", "fast"): (
        ("rc=constqp", "cq=28", "preset=p4"),
        ("-preset", "p4", "-rc", "constqp", "-cq", "25", "-profile:v", "main"),
    ),
    ("av1", "standard"): (
        ("rc=vbr", "b=12M", "maxrate=16M", "bufsize=24M", "preset=p5"),
        ("-preset", "p5", "-rc", "vbr", "-b:v", "12M", "-maxrate", "16M",
         "-bufsize", "24M", "-profile:v", "main"),
    ),
    ("av1", "high"): (
        ("rc=vbr", "b=22M", "maxrate=28M", "bufsize=34M", "preset=p6"),
        ("-preset", "p6", "-rc", "vbr", "-b:v", "22M", "-maxrate", "28M",
         "-bufsize", "34M", "-profile:v", "main"),
    ),
    ("av1", "archival"): (
        ("rc=vbr", "b=30M", "maxrate=38M", "bufsize=46M", "preset=p6"),
        ("-preset", "p6", "-rc", "vbr", "-b:v", "30M", "-maxrate", "38M",
         "-bufsize", "46M", "-profile:v", "main"),
    ),
    ("libx264", "fast"): (("crf=23", "preset=veryfast"), ("-preset", "veryfast", "-crf", "20")),
    ("libx264", "standard"): (("crf=18", "preset=medium", "vb=0", "profile=high"),
                              ("-preset", "medium", "-crf", "18", "-profile:v", "high")),
    ("libx264", "high"): (("crf=16", "preset=slow", "vb=0", "profile=high"),
                          ("-preset", "slow", "-crf", "16", "-profile:v", "high")),
    ("libx264", "archival"): (("crf=14", "preset=slow", "vb=0", "profile=high"),
                              ("-preset", "slow", "-crf", "14", "-profile:v", "high")),
    ("libx265", "fast"): (("crf=26", "preset=veryfast"), ("-preset", "veryfast", "-crf", "26")),
    ("libx265", "standard"): (("crf=24", "preset=medium"), ("-preset", "medium", "-crf", "24")),
    ("libx265", "high"): (("crf=22", "preset=slow"), ("-preset", "slow", "-crf", "22")),
    ("libx265", "archival"): (("crf=20", "preset=slow"), ("-preset", "slow", "-crf", "20")),
    ("libsvtav1", "fast"): (("crf=28", "preset=8"), ("-preset", "8", "-crf", "28")),
    ("libsvtav1", "standard"): (("crf=26", "preset=6"), ("-preset", "6", "-crf", "26")),
    ("libsvtav1", "high"): (("crf=24", "preset=4"), ("-preset", "4", "-crf", "24")),
    ("libsvtav1", "archival"): (("crf=22", "preset=2"), ("-preset", "2", "-crf", "22")),
}

# codec family -> candidate vcodecs in probe order; last entry is the CPU codec.
_FAMILY_VCODECS: dict[str, tuple[str, ...]] = {
    "h264": ("h264_nvenc", "h264_amf", "h264_qsv", "h264_vaapi", "libx264"),
    "hevc": ("hevc_nvenc", "libx265"),
    "av1": ("av1_nvenc", "libsvtav1"),
}

# only tiered GPU vcodecs map to a family policy row; lib* and amf/qsv/vaapi
# resolve to themselves (own _POLICY rows / _SPECS fallback).
_VCODEC_FAMILY: dict[str, str] = {
    vc: fam for fam, vcs in _FAMILY_VCODECS.items()
    for vc in vcs if vc.endswith("_nvenc")
}


def _tier_for(final: bool | None, tier: str | None) -> str:
    if tier is not None:
        if tier not in TIERS:
            raise ValueError(f"unknown quality tier {tier!r}; expected one of {TIERS}")
        return tier
    return "standard" if final else "fast"


def vcodec_for(backend: str | None, codec: str = "h264") -> str:
    """Resolve the codec family to the CPU or first-GPU candidate name."""
    if codec not in _FAMILY_VCODECS:
        raise ValueError(f"unknown codec {codec!r}; expected one of {sorted(_FAMILY_VCODECS)}")
    if resolve_backend(backend) == "cpu":
        return _FAMILY_VCODECS[codec][-1]
    return _FAMILY_VCODECS[codec][0]


def _tier_spec(vcodec: str, tier: str) -> EncoderSpec:
    family = _VCODEC_FAMILY.get(vcodec, vcodec)
    try:
        melt_args, ffmpeg_args = _POLICY[(family, tier)]
    except KeyError:
        melt_args, ffmpeg_args = _SPECS[(vcodec, tier != "fast")]
    return EncoderSpec(vcodec=vcodec, melt_args=melt_args, ffmpeg_args=ffmpeg_args)


def resolve_backend(requested: str | None = None) -> EncoderBackend:
    """Return ``gpu`` or ``cpu`` from explicit request or env default.

    Default is ``gpu`` (NVENC/AMF/QSV when available). Set
    ``OPEN_EDIT_RENDER_BACKEND=cpu`` to force software encoding.
    """
    if requested is not None and str(requested).strip():
        raw = str(requested).strip().lower()
    else:
        env = os.environ.get("OPEN_EDIT_RENDER_BACKEND")
        raw = "gpu" if env is None or not str(env).strip() else str(env).strip().lower()
    if raw in ("cpu", "software", "libx264"):
        return "cpu"
    return "gpu"


def _ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def _probe_encoder(vcodec: str, extra: list[str]) -> bool:
    """Return True if ffmpeg can encode a trivial frame with ``vcodec``.

    NVENC rejects frames smaller than ~128px, so the probe uses 256x256.
    """
    ffmpeg = _ffmpeg()
    if ffmpeg is None:
        return False
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.04",
        "-frames:v", "1", "-c:v", vcodec, *extra,
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except (subprocess.TimeoutExpired, OSError):
        return False
    return proc.returncode == 0


def select_encoder(backend: str | None = None, *, tier: str | None = None,
                   final: bool | None = None, codec: str = "h264") -> EncoderSpec:
    """Resolve (backend, tier, codec) to an EncoderSpec.

    ``tier`` wins over the legacy ``final`` flag (final=True -> standard,
    False/None -> fast). GPU backends probe the first working encoder of
    the family; non-tier vcodecs (amf/qsv/vaapi) fall back to the legacy
    ``_SPECS`` rows (final = tier != fast). CPU always yields the family's
    CPU codec; unknown/absent probes fall back to libx264.
    """
    resolved_tier = _tier_for(final, tier)
    if resolve_backend(backend) == "cpu":
        vcodec = _FAMILY_VCODECS[codec][-1]
    else:
        vcodec = None
        for candidate in _FAMILY_VCODECS[codec]:
            if candidate.endswith("_nvenc") or candidate in ("libx264", "libx265", "libsvtav1"):
                spec = _tier_spec(candidate, resolved_tier)
            else:
                spec = _SPECS[(candidate, resolved_tier != "fast")]
            if _probe_encoder(candidate, list(spec.ffmpeg_args)):
                vcodec = candidate
                break
        if vcodec is None:
            vcodec = "libx264"
    return _tier_spec(vcodec, resolved_tier)


def detect_gpu_vcodec(*, final: bool = False, codec: str = "h264") -> tuple[str, list[str]] | None:
    tier = _tier_for(final, None)
    for vcodec in _FAMILY_VCODECS[codec]:
        if vcodec.endswith("_nvenc") or vcodec in ("libx264", "libx265", "libsvtav1"):
            spec = _tier_spec(vcodec, tier)
        else:
            spec = _SPECS[(vcodec, tier != "fast")]
        if _probe_encoder(vcodec, list(spec.ffmpeg_args)):
            return vcodec, list(spec.ffmpeg_args)
    return None


def resolve_vcodec(backend: str | None = None, *, final: bool = False, codec: str = "h264") -> tuple[str, list[str]]:
    spec = select_encoder(backend, final=final, codec=codec)
    return spec.vcodec, list(spec.ffmpeg_args)


def apply_profile_vcodec(profile_vcodec: str, backend: str | None = None) -> str:
    return select_encoder(backend).vcodec


def ffmpeg_video_args(backend: str | None = None, *, final: bool = False) -> list[str]:
    spec = select_encoder(backend, final=final)
    return ["-c:v", spec.vcodec, *spec.ffmpeg_args]


def _override_pairs(vcodec: str, name: str, value: object) -> tuple[str, str]:
    if name == "crf":
        melt_key, ff_flag = ("cq", "-cq") if vcodec.endswith("_nvenc") else ("crf", "-crf")
    elif name == "vb":
        melt_key, ff_flag = "b", "-b:v"
    elif name == "preset":
        melt_key, ff_flag = "preset", "-preset"
    else:
        raise ValueError(f"unsupported override {name!r}")
    return melt_key, ff_flag


def apply_overrides(spec: EncoderSpec, overrides: dict) -> EncoderSpec:
    """Return a new spec with override args appended (last-wins)."""
    if not overrides:
        return spec
    melt = list(spec.melt_args)
    ff = list(spec.ffmpeg_args)
    for name in ("crf", "vb", "preset"):
        value = overrides.get(name)
        if value is None:
            continue
        melt_key, ff_flag = _override_pairs(spec.vcodec, name, value)
        melt.append(f"{melt_key}={value}")
        ff += [ff_flag, str(value)]
    return EncoderSpec(vcodec=spec.vcodec, melt_args=tuple(melt), ffmpeg_args=ff)
