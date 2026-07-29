"""Render profile selection and MLT consumer arg generation."""
from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel

from open_edit.render.encoder import EncoderBackend, apply_profile_vcodec


class RenderProfile(BaseModel):
    """A render profile (resolution, fps, codec)."""
    name: str
    width: int
    height: int
    frame_rate_num: int
    frame_rate_den: int
    vcodec: str = "libx264"
    acodec: str = "aac"
    encoder_backend: EncoderBackend | None = None


DEFAULT_PROFILES: list[RenderProfile] = [
    RenderProfile(name="1080p30", width=1920, height=1080, frame_rate_num=30, frame_rate_den=1),
    RenderProfile(name="1080p60", width=1920, height=1080, frame_rate_num=60, frame_rate_den=1),
    RenderProfile(name="720p30", width=1280, height=720, frame_rate_num=30, frame_rate_den=1),
    RenderProfile(name="480p30", width=854, height=480, frame_rate_num=30, frame_rate_den=1),
]

_PROFILE_BY_NAME: dict[str, RenderProfile] = {p.name: p for p in DEFAULT_PROFILES}


def select_profile(name: str) -> RenderProfile:
    """Look up a profile by name. Raises KeyError if not found."""
    if name not in _PROFILE_BY_NAME:
        raise KeyError(f"Unknown profile: {name}. Available: {list(_PROFILE_BY_NAME)}")
    return _PROFILE_BY_NAME[name]


def profile_to_mlt_args(
    profile: RenderProfile,
    backend: str | None = None,
    *,
    mode: str = "proxy",
) -> list[str]:
    """Convert a profile to melt consumer args.

    Final mode uses High profile + tighter quantizer so melt is not a
    low-bitrate destroy pass before ffmpeg overlay burn-in.
    """
    resolved_backend = backend or profile.encoder_backend
    if resolved_backend is None:
        resolved_backend = os.environ.get("OPEN_EDIT_RENDER_BACKEND", "gpu")
    vcodec = apply_profile_vcodec(profile.vcodec, resolved_backend)
    args = [
        f"s={profile.width}x{profile.height}",
        f"frame_rate_num={profile.frame_rate_num}",
        f"frame_rate_den={profile.frame_rate_den}",
        "progressive=1",
        "sample_aspect_num=1",
        "sample_aspect_den=1",
        "display_aspect_num=16",
        "display_aspect_den=9",
        "colorspace=709",
        f"vcodec={vcodec}",
        f"acodec={profile.acodec}",
    ]
    if mode == "final":
        # Match source-ish quality: High profile, strong bitrate floor.
        args += [
            "vprofile=high",
            "ab=320k",
            "frequency=48000",
            "channels=2",
        ]
        if vcodec == "libx264":
            # Source talk is ~6 Mbps High; CRF 18 + High keeps fidelity without bloat.
            args += ["crf=18", "preset=medium", "vb=0", "profile=high"]
        elif "nvenc" in vcodec:
            # VBR near source bitrate (talk ~6 Mbps) with headroom for overlays.
            args += [
                "rc=vbr",
                "b=10M",
                "maxrate=14M",
                "bufsize=20M",
                "preset=p5",
                "bf=2",
            ]
        elif "amf" in vcodec:
            args += ["quality=quality", "rc=vbr_peak", "b=10M", "maxrate=14M"]
        elif "qsv" in vcodec:
            args += ["global_quality=18", "preset=medium"]
        else:
            args += ["crf=18"]
    else:
        # Proxy: keep fast/small.
        args += ["ab=160k"]
        if vcodec == "libx264":
            args += ["crf=23", "preset=veryfast"]
        elif "nvenc" in vcodec:
            args += ["rc=constqp", "cq=23", "preset=p4"]
    return args
