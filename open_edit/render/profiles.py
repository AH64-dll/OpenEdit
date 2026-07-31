"""Render profile selection and MLT consumer arg generation."""
from __future__ import annotations

import os

from pydantic import BaseModel

from open_edit.render.encoder import select_encoder


class RenderProfile(BaseModel):
    """A render profile (resolution, fps, codec)."""
    name: str
    width: int
    height: int
    frame_rate_num: int
    frame_rate_den: int
    vcodec: str = "libx264"
    acodec: str = "aac"


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
    low-bitrate destroy pass before ffmpeg overlay burn-in. Codec quality
    args come from ``EncoderSpec.melt_args`` (single source in
    ``encoder.select_encoder``).
    """
    resolved_backend = backend or os.environ.get("OPEN_EDIT_RENDER_BACKEND", "gpu")
    spec = select_encoder(resolved_backend, final=(mode == "final"))
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
        f"vcodec={spec.vcodec}",
        f"acodec={profile.acodec}",
    ]
    if mode == "final":
        # Match source-ish quality: High profile, strong bitrate floor.
        args += [
            "vprofile=high",
            "ab=320k",
            "frequency=48000",
            "channels=2",
            *spec.melt_args,
        ]
    else:
        # Proxy: keep fast/small.
        args += ["ab=160k", *spec.melt_args]
    return args
