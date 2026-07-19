"""Render profile selection and MLT consumer arg generation."""
from __future__ import annotations

from pydantic import BaseModel


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


def profile_to_mlt_args(profile: RenderProfile) -> list[str]:
    """Convert a profile to melt consumer args."""
    return [
        f"s={profile.width}x{profile.height}",
        f"frame_rate_num={profile.frame_rate_num}",
        f"frame_rate_den={profile.frame_rate_den}",
        "progressive=1",
        "sample_aspect_num=1",
        "sample_aspect_den=1",
        "display_aspect_num=16",
        "display_aspect_den=9",
        "colorspace=709",
        f"vcodec={profile.vcodec}",
        f"acodec={profile.acodec}",
    ]
