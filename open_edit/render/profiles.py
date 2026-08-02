"""Render profile selection and MLT consumer arg generation."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, field_validator

from open_edit.render.encoder import (
    TIERS,
    EncoderSpec,
    apply_overrides,
    resolve_backend,
    select_encoder,
)

_KB = re.compile(r"^\d+[kKM]?$")
_SCALE = re.compile(r"^\d{2,5}x\d{2,5}$")
PreviewPlane = Literal["video", "audio", "mux"]
_PREVIEW_CHUNK_GEOMETRY = (640, 360)


class RenderProfile(BaseModel):
    """A render profile (resolution, fps, codec, quality)."""
    name: str
    width: int
    height: int
    frame_rate_num: int
    frame_rate_den: int
    vcodec: str = "libx264"
    acodec: str = "aac"
    quality: str | None = None
    crf: int | None = None
    vb: str | None = None
    preset: str | None = None
    scale: str | None = None
    codec: str | None = None
    ab: str | None = None

    @field_validator("quality")
    @classmethod
    def _quality_known(cls, v: str | None) -> str | None:
        if v is not None and v not in TIERS:
            raise ValueError(f"unknown quality {v!r}; expected one of {TIERS}")
        return v

    @field_validator("crf")
    @classmethod
    def _crf_range(cls, v: int | None) -> int | None:
        if v is not None and not (0 <= v <= 51):
            raise ValueError(f"crf must be in 0..51, got {v}")
        return v

    @field_validator("vb")
    @classmethod
    def _vb_shape(cls, v: str | None) -> str | None:
        if v is not None and not _KB.match(v):
            raise ValueError(f"vb must look like '10M', got {v!r}")
        return v

    @field_validator("scale")
    @classmethod
    def _scale_shape(cls, v: str | None) -> str | None:
        if v is not None and not _SCALE.match(v):
            raise ValueError(f"scale must look like '1920x1080', got {v!r}")
        return v

    @field_validator("codec")
    @classmethod
    def _codec_known(cls, v: str | None) -> str | None:
        if v is not None and v not in ("h264", "hevc", "av1"):
            raise ValueError(f"codec must be h264|hevc|av1, got {v!r}")
        return v

    @field_validator("preset")
    @classmethod
    def _preset_nonempty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("preset must not be empty")
        return v


def preview_chunk_profile(
    fps_num: int = 30,
    fps_den: int = 1,
) -> RenderProfile:
    """Build the bounded browser-safe profile used by preview chunks."""
    return RenderProfile(
        name="preview_chunk",
        width=_PREVIEW_CHUNK_GEOMETRY[0],
        height=_PREVIEW_CHUNK_GEOMETRY[1],
        frame_rate_num=fps_num,
        frame_rate_den=fps_den,
        vcodec="libx264",
        acodec="aac",
        quality="fast",
        ab="96k",
    )


DEFAULT_PROFILES: list[RenderProfile] = [
    RenderProfile(name="1080p30", width=1920, height=1080, frame_rate_num=30, frame_rate_den=1),
    RenderProfile(name="1080p60", width=1920, height=1080, frame_rate_num=60, frame_rate_den=1),
    RenderProfile(name="720p30", width=1280, height=720, frame_rate_num=30, frame_rate_den=1),
    RenderProfile(name="480p30", width=854, height=480, frame_rate_num=30, frame_rate_den=1),
    RenderProfile(name="fast_proxy", width=640, height=360, frame_rate_num=30, frame_rate_den=1),
    preview_chunk_profile(),
]

_PROFILE_BY_NAME: dict[str, RenderProfile] = {p.name: p for p in DEFAULT_PROFILES}


def select_profile(name: str) -> RenderProfile:
    """Look up a profile by name. Raises KeyError if not found."""
    if name not in _PROFILE_BY_NAME:
        raise KeyError(f"Unknown profile: {name}. Available: {list(_PROFILE_BY_NAME)}")
    return _PROFILE_BY_NAME[name]


def _mode_default_quality(mode: str) -> str:
    return "standard" if mode == "final" else "fast"


def profile_with_quality(
    profile_name: str | None,
    mode: str,
    quality: str | None = None,
    overrides: dict | None = None,
) -> RenderProfile:
    """Resolve a profile name + mode into a RenderProfile carrying quality.

    Defaults: profile None -> 1080p30 (final), preview_chunk
    (preview-chunks), or fast_proxy (proxy); quality None -> standard
    (final) / fast (other modes).
    """
    if not profile_name:
        if mode == "final":
            profile_name = "1080p30"
        elif mode in ("preview-chunks", "preview_chunks"):
            profile_name = "preview_chunk"
        else:
            profile_name = "fast_proxy"
    profile = select_profile(profile_name)
    if profile_name == "preview_chunk" and overrides:
        geometry_keys = (
            "width", "height", "frame_rate_num", "frame_rate_den", "scale",
        )
        attempted = [
            key for key in geometry_keys
            if overrides.get(key) is not None
        ]
        if attempted:
            raise ValueError(
                "preview_chunk geometry is fixed at 640x360; "
                f"overrides not allowed: {', '.join(attempted)}"
            )
    update: dict = {"quality": quality or _mode_default_quality(mode)}
    for key in ("crf", "vb", "preset", "scale", "codec", "ab"):
        if overrides and overrides.get(key) is not None:
            update[key] = overrides[key]
    return profile.model_copy(update=update)


def resolve_encoder_args(profile: RenderProfile, backend: str | None = None) -> EncoderSpec:
    """The EncoderSpec for a profile: tier (profile.quality) + raw overrides."""
    spec = select_encoder(backend, tier=profile.quality or "standard",
                          codec=profile.codec or "h264")
    overrides = {k: getattr(profile, k) for k in ("crf", "vb", "preset")
                 if getattr(profile, k) is not None}
    return apply_overrides(spec, overrides)


def profile_fingerprint(
    profile: RenderProfile,
    backend: str | None = None,
    *,
    plane: PreviewPlane | None = None,
) -> str:
    """Stable cache-key component: resolution + quality + overrides + backend."""
    parts = [profile.name, f"q={profile.quality or 'fast'}"]
    for key in ("crf", "vb", "preset", "scale", "codec", "ab"):
        value = getattr(profile, key)
        if value is not None:
            parts.append(f"{key}={value}")
    parts.append(f"enc={resolve_backend(backend)}")
    if plane is not None:
        if plane not in ("video", "audio", "mux"):
            raise ValueError(f"unknown preview plane {plane!r}")
        parts.append(f"plane={plane}")
    return "|".join(parts)


def preview_profile_fingerprint(
    profile: RenderProfile,
    plane: PreviewPlane,
    backend: str | None = None,
) -> str:
    """Return a stable, plane-specific preview profile identity."""
    if plane not in ("video", "audio", "mux"):
        raise ValueError(f"unknown preview plane {plane!r}")
    parts = [
        profile_fingerprint(profile, backend, plane=plane),
        f"size={profile.width}x{profile.height}",
        f"fps={profile.frame_rate_num}/{profile.frame_rate_den}",
        f"vcodec={profile.vcodec}",
        f"acodec={profile.acodec}",
        f"ab={profile.ab or '96k'}",
    ]
    return "|".join(parts)


def profile_to_mlt_args(
    profile: RenderProfile,
    backend: str | None = None,
    *,
    mode: str = "proxy",
) -> list[str]:
    spec = resolve_encoder_args(profile, backend)
    ab = profile.ab or ("320k" if mode == "final" else "96k")
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
        f"ab={ab}",
        "frequency=48000",
        "channels=2",
        *spec.melt_args,
    ]
    return args
