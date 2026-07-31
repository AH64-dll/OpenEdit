# Render Pipeline Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Single-pass melt→ffmpeg frame-server rendering with quality tiers + raw overrides, correct cache keys, hardware decode, and quality params surfaced through CLI/REST/agent tool.

**Architecture:** melt composes timeline frames and pipes raw video to ffmpeg, which applies Remotion overlays and does the single final encode (audio from a cheap separate melt pass). Quality is expressed as named tiers (fast/standard/high/archival) with optional raw overrides (crf/vb/preset/scale/codec), resolved by one function in `encoder.py`. The cache key gains a profile fingerprint. GPU backend emits `hwaccel=cuda` producers with one CPU-decode retry.

**Tech Stack:** Python 3.11, melt/MLT, ffmpeg (NVENC), pydantic v2, pytest.

## Global Constraints

- Python >= 3.11; pydantic >= 2.0 (use `model_copy(update=...)`, field validators).
- Ruff: line-length 100; select E,F,W,I,B,UP,N,SIM,C4,RUF.
- Preserve bit-identical defaults: `proxy` mode → 720p30 `fast`; `final` mode → 1080p30 `standard`. `fast` == old proxy args; `standard` == old final args, EXACTLY (see `_POLICY`).
- Do not break `select_encoder(backend, final=...)` callers: `final=True → tier="standard"`, `final=False/None → tier="fast"` when `tier` not given.
- Layering: agent tools may import `kernel`; `render/` may import `ir`, `storage`, `kernel`; `render/` must NOT import `serve`.
- All subprocess stderr must be captured and surfaced (never DEVNULL for error streams; use tempfile redirection to avoid pipe-buffer deadlocks).
- Tests: `pytest -o addopts="" -q <path>` for counts; default `addopts="-ra -q"` elsewhere.
- Test env quirk: stale `~/.local/bin/open_edit` may shadow the venv — always invoke tests via `/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest`.

## Locked Interfaces

```python
# render/encoder.py
TIERS = ("fast", "standard", "high", "archival")
def select_encoder(backend=None, *, tier=None, final=None, codec="h264") -> EncoderSpec
def apply_overrides(spec: EncoderSpec, overrides: dict) -> EncoderSpec
def vcodec_for(backend: str | None, codec: str = "h264") -> str          # resolved (not probed) codec name
# keep: resolve_backend, _probe_encoder, resolve_vcodec, ffmpeg_video_args, detect_gpu_vcodec, apply_profile_vcodec

# render/profiles.py
class RenderProfile(BaseModel):  # gains:
    quality: str | None = None        # None -> mode default (proxy=fast, final=standard)
    crf: int | None = None            # 0..51
    vb: str | None = None             # e.g. "10M"
    preset: str | None = None
    scale: str | None = None          # "WxH"
    codec: str | None = None          # "h264" | "hevc" | "av1"
    acodec: str = "aac"
    ab: str | None = None
def profile_with_quality(profile_name, mode, quality=None, overrides=None) -> RenderProfile
def resolve_encoder_args(profile: RenderProfile, backend=None) -> EncoderSpec
def profile_fingerprint(profile: RenderProfile, backend=None) -> str
def profile_to_mlt_args(profile, backend=None, *, mode="proxy") -> list[str]  # unchanged call shape

# render/pipe_builder.py
@dataclass(frozen=True)
class PipeCommands:
    melt_video_cmd: list[str]
    melt_audio_cmd: list[str]
    ffmpeg_cmd: list[str]
    audio_wav: Path
def build_pipe_commands(melt_bin, xml_path, output_mp4, profile, spec, overlays,
                        *, audio_bitrate="192k", workdir=None) -> PipeCommands
def overlay_filter_chain(overlays, width, height) -> list[str]  # pure, from graphics_overlay

# render/melt_runner.py
@dataclass
class PipeResult:
    returncode: int        # ffmpeg rc (or melt rc if melt failed first)
    melt_rc: int
    ffmpeg_rc: int
    stderr: str            # both processes, labeled
class PipeRunError(RuntimeError): ...
def run_pipe(cmds: PipeCommands, *, timeout_s: float) -> PipeResult

# render/emitter.py
def emit_timeline(timeline, config=None, asset_paths=None, *, hwaccel: bool = False) -> str

# render/cache.py
def render_cache_key(graph_hash: str, profile_fingerprint: str) -> str

# kernel/render_jobs.py
def enqueue(self, project_id, project_path, mode, *, expected_revision=None,
            allow_invalid_timeline=False, encoder_backend=None, params: dict | None = None) -> RenderJob

# render/orchestrator.py (signature extended by Task 3, body reworked by Task 5)
def render_project(project_id, project_dir, workdir, mode="proxy", profile_name=None,
                   quality=None, overrides=None, force=False, nice_level=10,
                   encoder_backend=None) -> RenderResult
```

---

## Task 1 (Track Q): Quality core — tiers, overrides, profiles

**Files:**
- Modify: `open_edit/render/encoder.py`
- Modify: `open_edit/render/profiles.py`
- Test: `tests/test_render/test_encoder.py` (append), `tests/test_render/test_profiles.py` (append)

**Interfaces:**
- Consumes: existing `EncoderSpec` (frozen dataclass: `vcodec`, `melt_args`, `ffmpeg_args`), `resolve_backend`, `_probe_encoder` (all keep working).
- Produces: `TIERS`, `select_encoder(tier=/final=/codec=)`, `apply_overrides`, `profile_with_quality`, `resolve_encoder_args`, `profile_fingerprint`, extended `RenderProfile` — consumed by Tasks 2, 4, 5.

- [ ] **Step 1: Write the failing tests**

`tests/test_render/test_encoder.py`:

```python
"""Quality tier model: default tiers are bit-identical to legacy args."""
import pytest

from open_edit.render.encoder import (
    TIERS, apply_overrides, select_encoder,
)


@pytest.fixture(autouse=True)
def _probe_all_encoders(monkeypatch):
    """Make encoder probing deterministic regardless of host hardware."""
    from open_edit.render import encoder as enc

    monkeypatch.setattr(enc, "_probe_encoder", lambda vcodec, extra: True)


def test_tiers_exist():
    assert TIERS == ("fast", "standard", "high", "archival")


def test_legacy_final_maps_to_standard():
    # final=True must equal old _SPECS final rows (bit-identical)
    assert select_encoder("gpu", final=True).vcodec == "h264_nvenc"
    spec = select_encoder("gpu", final=True)
    assert ("b=10M", "maxrate=14M") == (spec.melt_args[1], spec.melt_args[2])


def test_legacy_proxy_maps_to_fast():
    spec = select_encoder("gpu", final=False)
    assert spec.melt_args == ("rc=constqp", "cq=23", "preset=p4")


def test_cpu_default_unchanged():
    spec = select_encoder("cpu")
    assert spec.vcodec == "libx264"
    assert spec.melt_args == ("crf=23", "preset=veryfast")


def test_codec_override_hevc_cpu():
    spec = select_encoder("cpu", tier="standard", codec="hevc")
    assert spec.vcodec == "libx265"
    assert "-crf" in spec.ffmpeg_args and "24" in spec.ffmpeg_args


def test_codec_override_av1_cpu():
    spec = select_encoder("cpu", tier="standard", codec="av1")
    assert spec.vcodec == "libsvtav1"


def test_apply_overrides_appends_last_wins():
    spec = select_encoder("cpu", tier="standard")
    out = apply_overrides(spec, {"crf": 22, "preset": "slow"})
    assert out.ffmpeg_args[-4:] == ["-crf", "22", "-preset", "slow"]
    assert out.melt_args[-2:] == ("crf=22", "preset=slow")


def test_apply_overrides_nvenc_crf_uses_cq():
    spec = select_encoder("gpu", tier="standard")
    out = apply_overrides(spec, {"crf": 20})
    assert "-cq" in out.ffmpeg_args


def test_apply_overrides_empty_identity():
    spec = select_encoder("cpu", tier="high")
    assert apply_overrides(spec, {}) == spec
```

`tests/test_render/test_profiles.py` (append to existing file):

```python
"""Quality fields, resolution, fingerprint."""
import pytest
from pydantic import ValidationError

from open_edit.render.profiles import (
    RenderProfile, profile_fingerprint, profile_with_quality,
    resolve_encoder_args, select_profile,
)


def test_profile_with_quality_defaults_by_mode():
    p = profile_with_quality(None, "final")
    assert p.name == "1080p30" and p.quality == "standard"
    p2 = profile_with_quality(None, "proxy")
    assert p2.name == "720p30" and p2.quality == "fast"


def test_profile_with_quality_applies_overrides():
    p = profile_with_quality(None, "final", quality="high", overrides={"crf": 20})
    assert p.quality == "high" and p.crf == 20


def test_profile_validation_rejects_bad_values():
    with pytest.raises(ValidationError):
        RenderProfile(name="x", width=1, height=1, frame_rate_num=30,
                      frame_rate_den=1, quality="bogus")
    with pytest.raises(ValidationError):
        RenderProfile(name="x", width=1, height=1, frame_rate_num=30,
                      frame_rate_den=1, crf=99)
    with pytest.raises(ValidationError):
        RenderProfile(name="x", width=1, height=1, frame_rate_num=30,
                      frame_rate_den=1, codec="vp9")
    with pytest.raises(ValidationError):
        RenderProfile(name="x", width=1, height=1, frame_rate_num=30,
                      frame_rate_den=1, scale="1080px")


def test_resolve_encoder_args_standard_final_matches_legacy():
    p = profile_with_quality(None, "final")          # standard
    spec = resolve_encoder_args(p, "gpu")
    assert spec.vcodec == "h264_nvenc"
    assert "b=10M" in spec.melt_args


def test_fingerprint_differs_when_quality_differs():
    a = profile_fingerprint(profile_with_quality(None, "final", quality="fast"), "gpu")
    b = profile_fingerprint(profile_with_quality(None, "final", quality="standard"), "gpu")
    assert a != b
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest tests/test_render/test_encoder.py tests/test_render/test_profiles.py -o addopts="" -q`
Expected: FAIL (import errors — `TIERS` / `profile_with_quality` don't exist).

- [ ] **Step 3: Implement the tier model in encoder.py**

Replace the module-level `_SPECS`/`select_encoder` section with (keep `_probe_encoder`, `resolve_backend`, `_ffmpeg`, `EncoderSpec`, `_GPU_ORDER`; keep `_SPECS` for the amf/qsv/vaapi fallback rows — they stay keyed by `(vcodec, final)`):

```python
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

_VCODEC_FAMILY: dict[str, str] = {
    vc: fam for fam, vcs in _FAMILY_VCODECS.items() for vc in vcs
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


def _tier_spec(vcodec: str, tier: str) -> EncoderSpec:
    family = _VCODEC_FAMILY.get(vcodec, vcodec)
    try:
        melt_args, ffmpeg_args = _POLICY[(family, tier)]
    except KeyError:
        melt_args, ffmpeg_args = _SPECS[(vcodec, tier != "fast")]
    return EncoderSpec(vcodec=vcodec, melt_args=melt_args, ffmpeg_args=ffmpeg_args)
```

Then update the public helpers to keep their signatures but route through the new logic:

```python
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
```

And the override applier (append pairs; last wins in both dialects):

```python
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
    return EncoderSpec(vcodec=spec.vcodec, melt_args=tuple(melt), ffmpeg_args=tuple(ff))
```

- [ ] **Step 4: Implement the profile changes in profiles.py**

```python
import re
from pydantic import BaseModel, field_validator

from open_edit.render.encoder import (
    TIERS, apply_overrides, resolve_backend, select_encoder,
)

_KB = re.compile(r"^\d+[kKM]?$")
_SCALE = re.compile(r"^\d{2,5}x\d{2,5}$")


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
```

Then replace `profile_to_mlt_args` and add the resolvers:

```python
def _mode_default_quality(mode: str) -> str:
    return "standard" if mode == "final" else "fast"


def profile_with_quality(
    profile_name: str | None,
    mode: str,
    quality: str | None = None,
    overrides: dict | None = None,
) -> RenderProfile:
    """Resolve a profile name + mode into a RenderProfile carrying quality.

    Defaults: profile None -> 1080p30 (final) / 720p30 (proxy);
    quality None -> standard (final) / fast (proxy).
    """
    if not profile_name:
        profile_name = "1080p30" if mode == "final" else "720p30"
    profile = select_profile(profile_name)
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


def profile_fingerprint(profile: RenderProfile, backend: str | None = None) -> str:
    """Stable cache-key component: resolution + quality + overrides + backend."""
    parts = [profile.name, f"q={profile.quality or 'fast'}"]
    for key in ("crf", "vb", "preset", "scale", "codec"):
        value = getattr(profile, key)
        if value is not None:
            parts.append(f"{key}={value}")
    parts.append(f"enc={resolve_backend(backend)}")
    return "|".join(parts)
```

And update `profile_to_mlt_args` to use `resolve_encoder_args` (signature unchanged):

```python
def profile_to_mlt_args(
    profile: RenderProfile,
    backend: str | None = None,
    *,
    mode: str = "proxy",
) -> list[str]:
    spec = resolve_encoder_args(profile, backend)
    ab = profile.ab or ("320k" if mode == "final" else "160k")
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
```

- [ ] **Step 5: Run both test files to verify they pass**

Run: `/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest tests/test_render/test_encoder.py tests/test_render/test_profiles.py -o addopts="" -q`
Expected: PASS (all green).

- [ ] **Step 6: Run the pre-existing render tests**

Run: `/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest tests/test_render/ tests/test_windows_mcp.py -o addopts="" -q`
Expected: PASS (no legacy callers broken).

- [ ] **Step 7: Commit**

```bash
git add open_edit/render/encoder.py open_edit/render/profiles.py tests/test_render/test_encoder.py tests/test_render/test_profiles.py
git commit -m "feat(render): quality tier model (fast/standard/high/archival) + raw overrides + profile fingerprint"
```

---

## Task 2 (Track P): Frame-server pipe

**Files:**
- Create: `open_edit/render/pipe_builder.py`
- Modify: `open_edit/render/melt_runner.py`
- Modify: `open_edit/render/graphics_overlay.py` (reuse `overlay_filter_chain`)
- Test: `tests/test_render/test_pipe_builder.py` (new), `tests/test_render/test_run_pipe.py` (new)

**Interfaces:**
- Consumes: `EncoderSpec` (frozen dataclass), `RenderProfile`, `resolve_backend` — all unchanged by Task 1 (EncoderSpec shape persists).
- Produces: `PipeCommands`, `build_pipe_commands`, `overlay_filter_chain`, `OverlayClip` (MOVED here; graphics_overlay re-imports it), `run_pipe`, `PipeResult`, `PipeRunError` — consumed by Task 5.

- [ ] **Step 1: Write the failing tests**

`tests/test_render/test_pipe_builder.py`:

```python
"""Pipe command construction: melt rawvideo + audio pass + ffmpeg single encode."""
from pathlib import Path

from open_edit.render.encoder import select_encoder
from open_edit.render.pipe_builder import (
    OverlayClip, build_pipe_commands, overlay_filter_chain,
)
from open_edit.render.profiles import select_profile


def _fixture():
    profile = select_profile("720p30")
    spec = select_encoder("gpu", tier="standard")
    overlays = [
        OverlayClip(position_sec=1.0, duration_sec=2.0,
                    media_path=Path("/tmp/ov.mov"), label="card"),
    ]
    return profile, spec, overlays


def test_overlay_filter_chain_builds_inputs():
    overlays = [OverlayClip(position_sec=1.0, duration_sec=2.0,
                            media_path=Path("/tmp/ov.mov"))]
    filters = overlay_filter_chain(overlays, 1280, 720)
    assert isinstance(filters, list) and filters
    assert "overlay=" in "".join(filters)


def test_pipe_commands_shape(tmp_path: Path):
    profile, spec, overlays = _fixture()
    cmds = build_pipe_commands(
        "melt", Path("t.mlt"), tmp_path / "out.mp4", profile, spec, overlays,
        audio_bitrate="160k", workdir=tmp_path,
    )
    assert cmds.melt_video_cmd[0] == "melt"
    assert "avformat:pipe:" in cmds.melt_video_cmd
    assert "rawvideo" in " ".join(cmds.melt_video_cmd)
    assert cmds.melt_audio_cmd[-2:] == ["-format", "wav"]
    assert "video_off=1" in cmds.melt_audio_cmd
    assert "-f" in cmds.ffmpeg_cmd and "rawvideo" in cmds.ffmpeg_cmd
    assert cmds.ffmpeg_cmd[0] == "ffmpeg"
    assert str(tmp_path / "out.mp4") in cmds.ffmpeg_cmd
    assert str(cmds.audio_wav) in " ".join(cmds.melt_audio_cmd)
    assert " ".join(cmds.ffmpeg_cmd).count("-i") >= 2  # pipe + audio (+ overlays)


def test_pipe_commands_no_overlays(tmp_path: Path):
    profile, spec, _ = _fixture()
    cmds = build_pipe_commands(
        "melt", Path("t.mlt"), tmp_path / "out.mp4", profile, spec, [],
        audio_bitrate="160k", workdir=tmp_path,
    )
    assert "-map" in cmds.ffmpeg_cmd  # direct mapping, no filter_complex
    assert "filter_complex" not in cmds.ffmpeg_cmd


def test_pipe_commands_scale_override(tmp_path: Path):
    profile, spec, overlays = _fixture()
    profile = profile.model_copy(update={"scale": "640x360"})
    cmds = build_pipe_commands(
        "melt", Path("t.mlt"), tmp_path / "out.mp4", profile, spec, overlays,
        audio_bitrate="160k", workdir=tmp_path,
    )
    assert "s=640x360" in cmds.melt_video_cmd
    assert "-s" in cmds.ffmpeg_cmd and "640x360" in cmds.ffmpeg_cmd
```

`tests/test_render/test_run_pipe.py`:

```python
"""run_pipe: concurrent melt->ffmpeg execution with fake binaries."""
import subprocess
import sys
from pathlib import Path

import pytest

from open_edit.render.melt_runner import PipeRunError, run_pipe
from open_edit.render.pipe_builder import PipeCommands


def _fake_melt(path: Path, kind: str) -> Path:
    # fake melt: streams 10 raw frames to stdout (kind=video) or writes a
    # wav (kind=audio); kind=fail exits 1 after writing an error line.
    script = f"""#!/usr/bin/env python3
import sys
kind = {kind!r}
if kind == "video":
    sys.stdout.buffer.write(b"\\x00" * 1280 * 720 * 3 // 2)  # one 720p frame
    for _ in range(9):
        sys.stdout.buffer.write(b"\\x00" * 1280 * 720 * 3 // 2)
elif kind == "fail":
    sys.stderr.write("fake melt exploded\\n")
    sys.exit(1)
else:
    with open(sys.argv[sys.argv.index("avformat:") + 1][len("avformat:"):], "wb") as f:
        f.write(b"RIFF\\x00" * 4)
"""
    p = path / f"melt_{kind}.py"
    p.write_text(script)
    p.chmod(0o755)
    return p


def _fake_ffmpeg(path: Path, out_name: str) -> Path:
    # fake ffmpeg: consumes stdin fully, writes output file; kind=fail
    # exits 2 after writing stderr.
    script = f"""#!/usr/bin/env python3
import sys
data = sys.stdin.buffer.read()
out = [a for a in sys.argv if a.endswith(".mp4")][0]
open(out, "wb").write(data[:100] if data else b"")
sys.stderr.write("fake ffmpeg ok\\n")
"""
    p = path / "ffmpeg.py"
    p.write_text(script)
    p.chmod(0o755)
    return p


def _cmds(tmp_path: Path, *, melt_kind: str = "video") -> PipeCommands:
    melt = _fake_melt(tmp_path, melt_kind)
    ffmpeg = _fake_ffmpeg(tmp_path, "out.mp4")
    out = tmp_path / "out.mp4"
    audio_wav = tmp_path / "audio.wav"
    return PipeCommands(
        melt_video_cmd=[str(melt), "video"],
        melt_audio_cmd=[str(melt), "audio", "-consumer", f"avformat:{audio_wav}", "-format", "wav"],
        ffmpeg_cmd=[str(ffmpeg), "-i", "-", "-i", str(audio_wav), str(out)],
        audio_wav=audio_wav,
    )


def test_run_pipe_success(tmp_path: Path):
    result = run_pipe(_cmds(tmp_path), timeout_s=30)
    assert result.returncode == 0
    assert result.melt_rc == 0 and result.ffmpeg_rc == 0
    assert "fake ffmpeg ok" in result.stderr


def test_run_pipe_audio_pass_failure(tmp_path: Path):
    result = run_pipe(_cmds(tmp_path, melt_kind="fail"), timeout_s=30)
    assert result.returncode != 0
    assert "fake melt exploded" in result.stderr


def test_run_pipe_melt_failure(tmp_path: Path):
    cmds = _cmds(tmp_path)
    cmds = PipeCommands([sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"],
                        cmds.melt_audio_cmd, cmds.ffmpeg_cmd, cmds.audio_wav)
    result = run_pipe(cmds, timeout_s=30)
    assert result.returncode == 3
    assert "boom" in result.stderr


def test_run_pipe_ffmpeg_failure(tmp_path: Path):
    cmds = _cmds(tmp_path)
    bad_ff = tmp_path / "ff_fail.py"
    bad_ff.write_text("#!/usr/bin/env python3\nimport sys\nsys.stdin.buffer.read()\nsys.stderr.write('ff died')\nsys.exit(2)\n")
    bad_ff.chmod(0o755)
    cmds = PipeCommands(cmds.melt_video_cmd, cmds.melt_audio_cmd,
                        [str(bad_ff), "-i", "-", str(tmp_path / "x.mp4")], cmds.audio_wav)
    result = run_pipe(cmds, timeout_s=30)
    assert result.returncode == 2
    assert "ff died" in result.stderr


def test_run_pipe_timeout(tmp_path: Path):
    cmds = _cmds(tmp_path)
    slow_ff = tmp_path / "ff_slow.py"
    slow_ff.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(60)\n")
    slow_ff.chmod(0o755)
    cmds = PipeCommands(cmds.melt_video_cmd, cmds.melt_audio_cmd,
                        [str(slow_ff)], cmds.audio_wav)
    with pytest.raises(PipeRunError, match="timed out"):
        run_pipe(cmds, timeout_s=1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest tests/test_render/test_pipe_builder.py tests/test_render/test_run_pipe.py -o addopts="" -q`
Expected: FAIL (import errors — `pipe_builder` doesn't exist, `run_pipe` missing).

- [ ] **Step 3: Create pipe_builder.py**

```python
"""Frame-server pipe: melt -> rawvideo stdout -> ffmpeg single encode.

melt composes the timeline and streams raw frames; ffmpeg applies the
Remotion overlays and performs the single final encode. Audio comes from a
separate cheap melt pass (``video_off=1``) muxed by ffmpeg.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from open_edit.render.encoder import EncoderSpec
from open_edit.render.graphics_overlay import OverlayClip
from open_edit.render.profiles import RenderProfile


@dataclass(frozen=True)
class PipeCommands:
    """The three subprocess commands of one frame-server render."""
    melt_video_cmd: list[str]
    melt_audio_cmd: list[str]
    ffmpeg_cmd: list[str]
    audio_wav: Path


def _fps_string(profile: RenderProfile) -> str:
    if profile.frame_rate_den == 1:
        return str(profile.frame_rate_num)
    return f"{profile.frame_rate_num}/{profile.frame_rate_den}"


def _size(profile: RenderProfile) -> str:
    if profile.scale:
        return profile.scale
    return f"{profile.width}x{profile.height}"


def overlay_filter_chain(overlays: list[OverlayClip], width: int, height: int) -> list[str]:
    """Filter-graph fragments for the overlay burn (pure; ported from
    ``graphics_overlay.burn_overlays``). Returns one filter per overlay
    window; the caller joins with ``;`` and maps the last label ``[vout]``."""
    filters: list[str] = []
    last = "[0:v]"
    for i, ov in enumerate(overlays, start=1):
        end = ov.position_sec + ov.duration_sec
        out_label = f"[v{i}]" if i < len(overlays) else "[vout]"
        if ov.alpha:
            filters.append(
                f"[{i + 1}:v]scale={width}:{height},"
                f"format=rgba,"
                f"setpts=PTS-STARTPTS+{ov.position_sec}/TB[ov{i}]"
            )
        else:
            filters.append(
                f"[{i + 1}:v]scale={width}:{height},"
                f"setpts=PTS-STARTPTS+{ov.position_sec}/TB[ov{i}]"
            )
        filters.append(
            f"{last}[ov{i}]overlay=0:0:format=auto:eof_action=pass:"
            f"enable='between(t,{ov.position_sec:.3f},{end:.3f})'"
            f"{out_label}"
        )
        last = f"[v{i}]"
    return filters


def build_pipe_commands(
    melt_bin: str,
    xml_path: Path,
    output_mp4: Path,
    profile: RenderProfile,
    spec: EncoderSpec,
    overlays: list[OverlayClip],
    *,
    audio_bitrate: str = "192k",
    workdir: Path | None = None,
) -> PipeCommands:
    """Build melt-video, melt-audio, and ffmpeg commands for one render."""
    size = _size(profile)
    fps = _fps_string(profile)
    audio_wav = (workdir or output_mp4.parent) / f"{output_mp4.stem}.audio.wav"

    melt_video_cmd = [
        melt_bin, str(xml_path),
        "-consumer", "avformat:pipe:",
        "-format", "rawvideo",
        "-vcodec", "rawvideo",
        "-pix_fmt", "yuv420p",
        f"s={size}",
        f"frame_rate_num={profile.frame_rate_num}",
        f"frame_rate_den={profile.frame_rate_den}",
        "progressive=1",
        "colorspace=709",
    ]

    melt_audio_cmd = [
        melt_bin, str(xml_path),
        "-consumer", f"avformat:{audio_wav}",
        "-format", "wav",
        "video_off=1",
    ]

    video_inputs = ["-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", size, "-r", fps, "-i", "-"]
    audio_inputs = ["-i", str(audio_wav)]
    overlay_inputs: list[str] = []
    for ov in overlays:
        overlay_inputs += ["-i", str(ov.media_path)]

    if overlays:
        filters = overlay_filter_chain(overlays, *map(int, size.split("x")))
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            *video_inputs, *audio_inputs, *overlay_inputs,
            "-filter_complex", ";".join(filters),
            "-map", "[vout]", "-map", "1:a?",
            "-c:v", spec.vcodec, *spec.ffmpeg_args,
            "-c:a", profile.acodec, "-b:a", audio_bitrate,
            str(output_mp4),
        ]
    else:
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            *video_inputs, *audio_inputs,
            "-map", "0:v", "-map", "1:a?",
            "-c:v", spec.vcodec, *spec.ffmpeg_args,
            "-c:a", profile.acodec, "-b:a", audio_bitrate,
            str(output_mp4),
        ]

    return PipeCommands(
        melt_video_cmd=melt_video_cmd,
        melt_audio_cmd=melt_audio_cmd,
        ffmpeg_cmd=ffmpeg_cmd,
        audio_wav=audio_wav,
    )
```

Note: the overlay filter input index is `i + 1` because input 0 is the pipe and input 1 is audio.

- [ ] **Step 4: Add run_pipe to melt_runner.py**

Append to `open_edit/render/melt_runner.py`:

```python
class PipeRunError(RuntimeError):
    """Raised when a frame-server pipe fails or exceeds its wall-clock budget."""


@dataclasses.dataclass
class PipeResult:
    """Outcome of a frame-server pipe run."""
    returncode: int
    melt_rc: int
    ffmpeg_rc: int
    stderr: str


def run_pipe(cmds: "PipeCommands", *, timeout_s: float) -> PipeResult:
    """Run melt (video -> raw pipe) and ffmpeg concurrently; audio pass first.

    stderr of both processes is captured via temp files (no pipe-buffer
    deadlock) and merged with ``melt:`` / ``ffmpeg:`` labels. ffmpeg's
    exit drives the result; a melt failure aborts before ffmpeg starts.
    """
    import subprocess
    import tempfile
    import time as _time

    from open_edit.render.pipe_builder import PipeCommands

    def _exec_sync(cmd: list[str], label: str) -> tuple[int, str]:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        return proc.returncode, proc.stderr or ""

    # 1) Audio pass first (fast: video_off=1). ffmpeg opens it at startup.
    try:
        audio_rc, audio_err = _exec_sync(cmds.melt_audio_cmd, "melt-audio")
    except subprocess.TimeoutExpired:
        raise PipeRunError(f"melt-audio timed out after {timeout_s:g}s") from None
    if audio_rc != 0:
        return PipeResult(audio_rc, audio_rc, -1, f"melt-audio failed:\n{audio_err.strip()}")

    # 2) Video pipe: melt -> ffmpeg.
    deadline = _time.monotonic() + timeout_s
    with tempfile.TemporaryFile() as melt_err_f, tempfile.TemporaryFile() as ff_err_f:
        try:
            melt = subprocess.Popen(
                cmds.melt_video_cmd, stdout=subprocess.PIPE, stderr=melt_err_f,
            )
            ffmpeg = subprocess.Popen(
                cmds.ffmpeg_cmd, stdin=melt.stdout, stderr=ff_err_f,
            )
        except OSError as exc:
            raise PipeRunError(f"pipe spawn failed: {exc}") from None
        melt.stdout.close()
        try:
            ffmpeg_rc = ffmpeg.wait(timeout=max(0.5, deadline - _time.monotonic()))
        except subprocess.TimeoutExpired:
            melt.kill()
            ffmpeg.kill()
            melt.wait()
            ffmpeg.wait()
            raise PipeRunError(f"render pipe timed out after {timeout_s:g}s") from None
        try:
            melt_rc = melt.wait(timeout=30)
        except subprocess.TimeoutExpired:
            melt.kill()
            melt_rc = melt.wait()
        melt_err_f.seek(0)
        ff_err_f.seek(0)
        melt_err = melt_err_f.read().decode("utf-8", errors="replace").strip()
        ff_err = ff_err_f.read().decode("utf-8", errors="replace").strip()

    stderr = "\n".join(
        part for part in (
            f"melt (rc={melt_rc}): {melt_err[-400:]}" if melt_err else "",
            f"ffmpeg (rc={ffmpeg_rc}): {ff_err[-400:]}" if ff_err else "",
        ) if part
    )
    # ffmpeg's rc wins when it failed (melt usually dies of broken pipe then);
    # otherwise surface melt's failure (fake-ffmpeg succeeded but melt broke).
    if ffmpeg_rc != 0:
        return PipeResult(ffmpeg_rc, melt_rc, ffmpeg_rc, stderr)
    if melt_rc != 0:
        return PipeResult(melt_rc, melt_rc, ffmpeg_rc, stderr)
    return PipeResult(0, 0, 0, stderr)
```

- [ ] **Step 5: Refactor graphics_overlay.py to reuse the filter chain**

Replace the filter-building block in `burn_overlays` (the `for i, ov in enumerate(...)` loop building `filters`) with:

```python
    from open_edit.render.pipe_builder import OverlayClip, overlay_filter_chain

    filters = overlay_filter_chain(overlays, width, height)
```

and delete the now-unused local loop and the local `OverlayClip` dataclass (import it from `pipe_builder` instead, keeping the name re-exported for any external importers). `burn_overlays` keeps its signature and semantics (used until Task 5 removes it); its existing tests must stay green.

- [ ] **Step 6: Run the new tests**

Run: `/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest tests/test_render/test_pipe_builder.py tests/test_render/test_run_pipe.py tests/test_render/ -o addopts="" -q`
Expected: PASS (all render tests, including the refactored graphics_overlay).

- [ ] **Step 7: Commit**

```bash
git add open_edit/render/pipe_builder.py open_edit/render/melt_runner.py open_edit/render/graphics_overlay.py tests/test_render/test_pipe_builder.py tests/test_render/test_run_pipe.py
git commit -m "feat(render): frame-server pipe (melt rawvideo -> ffmpeg single encode) + run_pipe"
```

---

## Task 3 (Track S): Surfaces — jobs params, CLI, REST, agent tool

**Files:**
- Modify: `open_edit/kernel/render_jobs.py`
- Modify: `open_edit/cli.py`
- Modify: `open_edit/serve/routers/renders.py`
- Modify: `open_edit/kernel/tool_registry.py` (TriggerRenderArgs fields)
- Modify: `open_edit/kernel/tool_executor.py` (`_run_trigger_render` forwarding)
- Modify: `open_edit/render/orchestrator.py` (signature + one line — see Step 4)
- Test: `tests/test_serve_render_jobs.py` (append), `tests/test_tool_executor.py` (append), `tests/test_render_jobs.py` (append)

**Interfaces:**
- Consumes: `RenderJobService.enqueue` extension (this task), `profile_with_quality` from Task 1, CLI `render` parser (this task).
- Produces: `enqueue(..., params=...)` + `params_json` persistence, CLI flags, REST fields, trigger_render schema fields — consumed by Task 5 (orchestrator body) and integration.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_render_jobs.py`:

```python
def test_enqueue_persists_params(tmp_path: Path) -> None:
    from open_edit.kernel.render_jobs import RenderJobService
    from open_edit.storage.edit_graph import EditGraphStore
    db = tmp_path / ".open_edit"
    db.mkdir(parents=True)
    store = EditGraphStore(db / "edit_graph.db")
    service = RenderJobService()
    try:
        job = service.enqueue(
            "proj", tmp_path, "final",
            params={"profile": "1080p30", "quality": "high", "crf": 20},
        )
        persisted = service.get(tmp_path, job.job_id)
        assert persisted is not None
        assert persisted.params == {"profile": "1080p30", "quality": "high", "crf": 20}
    finally:
        for task in service._tasks.values():
            task.cancel()


def test_launch_command_includes_params(tmp_path: Path) -> None:
    import asyncio
    from open_edit.kernel.render_jobs import RenderJobService
    from open_edit.storage.edit_graph import EditGraphStore
    db = tmp_path / ".open_edit"
    db.mkdir(parents=True)
    EditGraphStore(db / "edit_graph.db")
    service = RenderJobService()
    try:
        job = service.enqueue(
            "proj", tmp_path, "final",
            params={"quality": "high", "crf": 20, "scale": "640x360", "codec": "hevc"},
        )
        # _launch builds the command before any subprocess runs; we only
        # assert the command shape via a spy on create_subprocess_exec.
        captured: dict = {}

        async def fake_exec(*args, **kwargs):
            captured["cmd"] = args[0]
            import asyncio as aio
            proc = aio.subprocess.Process(
                transport=None, protocol=None, loop=aio.get_running_loop(),
            )
            proc.returncode = 0
            return proc

        original = asyncio.create_subprocess_exec
        asyncio.create_subprocess_exec = fake_exec
        try:
            asyncio.run(service._launch(tmp_path, job.job_id, "final"))
        except Exception:
            pass
        finally:
            asyncio.create_subprocess_exec = original
        cmd = captured.get("cmd", [])
        assert "--quality" in cmd and "high" in cmd
        assert "--crf" in cmd and "20" in cmd
        assert "--scale" in cmd and "640x360" in cmd
        assert "--codec" in cmd and "hevc" in cmd
    finally:
        for task in service._tasks.values():
            task.cancel()
```

Append to `tests/test_serve_render_jobs.py`:

```python
def test_render_request_accepts_quality_params() -> None:
    from open_edit.serve.routers.renders import RenderRequest

    req = RenderRequest(mode="final", quality="high", crf=20, scale="640x360", codec="hevc")
    assert req.quality == "high" and req.crf == 20 and req.codec == "hevc"


def test_render_request_rejects_bad_quality() -> None:
    from pydantic import ValidationError

    from open_edit.serve.routers.renders import RenderRequest

    try:
        RenderRequest(quality="bogus")
        assert False, "expected ValidationError"
    except ValidationError:
        pass
```

Append to `tests/test_tool_executor.py`:

```python
def test_trigger_render_forwards_quality_params(tmp_path: Path, monkeypatch) -> None:
    import asyncio

    from open_edit.kernel import tool_executor
    from open_edit.kernel.render_jobs import RenderJobService

    captured: dict = {}
    original = RenderJobService.enqueue

    def fake_enqueue(self, project_id, project_path, mode, **kwargs):
        captured.update(kwargs)
        import uuid
        from open_edit.kernel.render_jobs import RenderJob
        return RenderJob(uuid.uuid4().hex, project_id, mode, "queued", 0.0, 0.0)

    monkeypatch.setattr(RenderJobService, "enqueue", fake_enqueue)
    monkeypatch.setattr(tool_executor, "validate_or_error", lambda *a, **k: None)
    monkeypatch.setattr(tool_executor, "_strip_injected_project_id", lambda t, a: a)
    result = asyncio.run(tool_executor._run_trigger_render(
        {"mode": "final", "quality": "high", "crf": 20, "scale": "640x360", "codec": "hevc", "wait": False},
        tmp_path,
    ))
    assert result.get("ok") is True
    params = captured.get("params", {})
    assert params["quality"] == "high" and params["crf"] == 20
    assert params["codec"] == "hevc"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest tests/test_render_jobs.py tests/test_serve_render_jobs.py tests/test_tool_executor.py -o addopts="" -q`
Expected: FAIL (no `params` on enqueue / RenderJob, no schema fields).

- [ ] **Step 3: render_jobs.py — params persistence**

- Extend `RenderJob` dataclass: `params: dict | None = None` (after `edit_graph_hash`).
- Extend `_SCHEMA` with `params_json TEXT` (append the column to the CREATE TABLE).
- In `_ensure_schema`: after the existing `qc_report` ALTER, add:

```python
        if "params_json" not in cols:
            con.execute("ALTER TABLE render_jobs ADD COLUMN params_json TEXT")
```

- `_row`: `params=json.loads(row["params_json"]) if "params_json" in keys and row["params_json"] else None,`
- `enqueue(..., params: dict | None = None)`: pass `params` into the INSERT (`params_json`) and into the returned `RenderJob`; for the coalesced-existing branch, keep the stored params (job already persisted). (`_update` is unchanged — params are write-once at enqueue.)
- `_launch`: after building `command = [sys.executable, "-m", "open_edit.cli", "render", "--mode", mode, "--json"]`, insert:

```python
        job = self.get(project_path, job_id)
        params = (job.params if job is not None else None) or {}
        for key, flag in (("profile", "--profile"), ("quality", "--quality"),
                          ("crf", "--crf"), ("vb", "--vb"), ("preset", "--preset"),
                          ("scale", "--scale"), ("codec", "--codec")):
            value = params.get(key)
            if value is not None:
                command += [flag, str(value)]
```

- [ ] **Step 4: cli.py — flags + render_project signature**

Add to `p_render` (after `--encoder`):

```python
    p_render.add_argument("--quality", default=None, choices=["fast", "standard", "high", "archival"],
                          help="encode quality tier (default: fast for proxy, standard for final)")
    p_render.add_argument("--crf", type=int, default=None, help="quality override 0-51 (nvenc: mapped to cq)")
    p_render.add_argument("--vb", default=None, help="video bitrate override, e.g. 10M")
    p_render.add_argument("--preset", default=None, help="encoder preset override")
    p_render.add_argument("--scale", default=None, help="output scale override, e.g. 1280x720")
    p_render.add_argument("--codec", default=None, choices=["h264", "hevc", "av1"],
                          help="codec family override")
```

In `cmd_render`, build the overrides dict and pass through:

```python
    overrides = {k: v for k, v in (
        ("crf", args.crf), ("vb", args.vb), ("preset", args.preset),
        ("scale", args.scale), ("codec", args.codec),
    ) if v is not None}
    result = render_project(
        project_id=...,  # keep existing expression
        project_dir=project_dir,
        workdir=project_dir / "renders",
        mode=args.mode,
        profile_name=args.profile,
        quality=args.quality,
        overrides=overrides,
        force=args.force,
        nice_level=10,
        encoder_backend=args.encoder,
    )
```

(Keep every existing argument the current call passes — read the current `cmd_render` body and preserve `project_id`/`force` handling.)

In `orchestrator.py`, extend the signature and the profile line (the ONLY change this task makes to this file):

```python
def render_project(
    project_id: str,
    project_dir: Path,
    workdir: Path,
    mode: Literal["proxy", "final"] = "proxy",
    profile_name: Optional[str] = None,
    quality: Optional[str] = None,
    overrides: Optional[dict] = None,
    force: bool = False,
    nice_level: int = 10,
    encoder_backend: Optional[str] = None,
) -> RenderResult:
    ...
    profile = profile_with_quality(profile_name, mode, quality, overrides)
```

replacing the current `profile_name`/`select_profile` lines (import `profile_with_quality` from `open_edit.render.profiles`).

- [ ] **Step 5: renders.py — RenderRequest fields**

```python
class RenderRequest(BaseModel):
    mode: str = "proxy"  # "proxy" | "final" | "overlay"
    expected_revision: int | None = None
    encoder: str | None = None  # "gpu" (default) | "cpu"
    profile: str | None = None
    quality: str | None = None
    crf: int | None = None
    vb: str | None = None
    preset: str | None = None
    scale: str | None = None
    codec: str | None = None
```

In `post_render`, validate and forward:

```python
    quality = (req.quality or "").strip().lower() or None
    if quality is not None and quality not in ("fast", "standard", "high", "archival"):
        raise HTTPException(status_code=400, detail="quality must be fast|standard|high|archival")
    codec = (req.codec or "").strip().lower() or None
    if codec is not None and codec not in ("h264", "hevc", "av1"):
        raise HTTPException(status_code=400, detail="codec must be h264|hevc|av1")
    params = {k: v for k, v in (
        ("profile", req.profile), ("quality", quality), ("crf", req.crf),
        ("vb", req.vb), ("preset", req.preset), ("scale", req.scale), ("codec", codec),
    ) if v is not None}
    job = DEFAULT_RENDER_JOB_SERVICE.enqueue(
        project_id, project_path, req.mode,
        expected_revision=req.expected_revision,
        encoder_backend=encoder,
        params=params or None,
    )
```

- [ ] **Step 6: tool_registry.py + tool_executor.py — trigger_render schema and forwarding**

In `tool_registry.py`, extend `TriggerRenderArgs` (keep `extra="forbid"`; add fields):

```python
    quality: str | None = None
    profile: str | None = None
    crf: int | None = None
    vb: str | None = None
    preset: str | None = None
    scale: str | None = None
    codec: str | None = None
```

(Read the current class to match field style/descriptions.)

In `tool_executor.py`, in `_run_trigger_render`, after the `encoder` block, validate + build params:

```python
    quality = args.get("quality")
    if quality is not None and str(quality).lower() not in ("fast", "standard", "high", "archival"):
        return {"ok": False, "error": f"invalid quality {quality!r}", "error_code": "schema_validation_failed"}
    codec = args.get("codec")
    if codec is not None and str(codec).lower() not in ("h264", "hevc", "av1"):
        return {"ok": False, "error": f"invalid codec {codec!r}", "error_code": "schema_validation_failed"}
    params = {k: v for k, v in (
        ("profile", args.get("profile")), ("quality", str(quality).lower() if quality else None),
        ("crf", args.get("crf")), ("vb", args.get("vb")), ("preset", args.get("preset")),
        ("scale", args.get("scale")), ("codec", str(codec).lower() if codec else None),
    ) if v is not None}
```

and change the enqueue call to `DEFAULT_RENDER_JOB_SERVICE.enqueue(project_path.name, project_path, mode, encoder_backend=encoder, params=params or None)`.

- [ ] **Step 7: Run the surface tests**

Run: `/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest tests/test_render_jobs.py tests/test_serve_render_jobs.py tests/test_tool_executor.py tests/test_serve_pi_bridge.py -o addopts="" -q`
Expected: PASS.

- [ ] **Step 8: Run the full suite**

Run: `/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest -o addopts="" -q tests/`
Expected: PASS (0 failed). If a CLI test asserts the exact render command shape, update it to include the new flags only when present.

- [ ] **Step 9: Commit**

```bash
git add open_edit/kernel/render_jobs.py open_edit/kernel/tool_registry.py open_edit/kernel/tool_executor.py open_edit/cli.py open_edit/serve/routers/renders.py open_edit/render/orchestrator.py tests/
git commit -m "feat(render): quality params through render jobs, CLI, REST, and trigger_render tool"
```

---

## Task 4 (Track H): hwaccel emitter + cache key helper

**Files:**
- Modify: `open_edit/render/emitter.py`
- Modify: `open_edit/render/cache.py`
- Test: `tests/test_render/test_emitter.py` (append), `tests/test_render/test_cache.py` (append)

**Interfaces:**
- Consumes: `Timeline`/`EmitterConfig` (unchanged), `profile_fingerprint` from Task 1 (only for its own test of `render_cache_key` composition — keep Task 4's unit test self-contained with a literal fingerprint string).
- Produces: `emit_timeline(..., *, hwaccel: bool)`, `render_cache_key(graph_hash, profile_fingerprint)` — consumed by Task 5.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_render/test_emitter.py`:

```python
def test_emit_timeline_hwaccel_properties(tmp_path: Path) -> None:
    from open_edit.ir.types import Asset, Clip, Project, Track, Timeline
    from open_edit.render.emitter import EmitterConfig, emit_timeline

    asset = Asset(asset_hash="abc123", filename="a.mp4", duration_sec=1.0,
                  width=1920, height=1080, alignment=[])
    clip = Clip(clip_id="c1", asset_hash="abc123", track_id="v1",
                position_sec=0.0, in_point_sec=0.0, out_point_sec=1.0)
    timeline = Timeline(
        project_id="p1", name="p1", workdir=str(tmp_path),
        duration_sec=1.0, assets=[asset], tracks=[Track(track_id="v1", clips=[clip])],
    )
    xml_off = emit_timeline(timeline, EmitterConfig())
    xml_on = emit_timeline(timeline, EmitterConfig(), hwaccel=True)
    assert "hwaccel" not in xml_off
    assert 'name="hwaccel">cuda' in xml_on
    assert 'name="hwaccel_device">0' in xml_on
```

Append to `tests/test_render/test_cache.py`:

```python
def test_render_cache_key_composes() -> None:
    from open_edit.render.cache import render_cache_key

    key = render_cache_key("hash1", "1080p30|q=standard|enc=gpu")
    assert key == "hash1|1080p30|q=standard|enc=gpu"
    assert key != render_cache_key("hash1", "720p30|q=fast|enc=gpu")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest tests/test_render/test_emitter.py tests/test_render/test_cache.py -o addopts="" -q`
Expected: FAIL (`hwaccel` kwarg unsupported / `render_cache_key` missing).

- [ ] **Step 3: emitter.py — hwaccel flag**

- Change the signature to `def emit_timeline(timeline, config=None, asset_paths=None, *, hwaccel: bool = False) -> str`.
- In the producer loop (the `etree.SubElement(root, "producer", ...)` block at emitter.py:196), append property children when `hwaccel`:

```python
        producer = etree.SubElement(root, "producer", attrib={
            "id": f"producer_{asset_hash}",
            "resource": resource,
        })
        if hwaccel:
            etree.SubElement(producer, "property", attrib={"name": "hwaccel"}).text = "cuda"
            etree.SubElement(producer, "property", attrib={"name": "hwaccel_device"}).text = "0"
```

- [ ] **Step 4: cache.py — render_cache_key**

```python
def render_cache_key(graph_hash: str, profile_fingerprint: str) -> str:
    """Cache key = graph hash + profile identity (resolution/quality/overrides/encoder)."""
    return f"{graph_hash}|{profile_fingerprint}"
```

- [ ] **Step 5: Run the tests**

Run: `/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest tests/test_render/test_emitter.py tests/test_render/test_cache.py tests/test_render/ -o addopts="" -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add open_edit/render/emitter.py open_edit/render/cache.py tests/test_render/test_emitter.py tests/test_render/test_cache.py
git commit -m "feat(render): hwaccel=cuda producer emission + profile-scoped render cache key"
```

---

## Task 5 (serial): Orchestrator integration + end-to-end test

> Depends on Tasks 1, 2, 4 being merged (uses `profile_with_quality`, `build_pipe_commands`, `run_pipe`, `emit_timeline(hwaccel=)`, `render_cache_key`). Task 3's one-line orchestrator change (signature + `profile_with_quality`) is already in `render_project` — keep it.

**Files:**
- Modify: `open_edit/render/orchestrator.py` (rework the melt/burn section)
- Delete: `open_edit/render/graphics_overlay.py` (after removing the orchestrator import)
- Test: `tests/test_render/test_orchestrator.py` (append), `tests/test_e2e_render.py` (append)

**Interfaces:**
- Consumes: `PipeCommands`/`build_pipe_commands`, `run_pipe`/`PipeResult`/`PipeRunError`, `profile_fingerprint`/`profile_with_quality`, `render_cache_key`, `emit_timeline(hwaccel=)`, `MeltTimeoutError` (now raised only by the legacy MeltRunner path — drop the import if unused).
- Produces: the final `render_project` behavior (single pass, cache-keyed on profile, hwaccel retry).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_render/test_orchestrator.py`:

```python
def _make_project(tmp_path: Path, *, name: str = "proj"):
    """Ingest one fixture clip and apply one AddClipOp (mirrors test_e2e_render)."""
    from pathlib import Path

    from open_edit.ir.types import AddClipOp, Project
    from open_edit.storage.assets import AssetStore
    from open_edit.storage.edit_graph import EditGraphStore

    TESTDATA = Path(__file__).resolve().parents[1] / "testdata" / "raw_videos"
    project_dir = tmp_path / name
    open_edit_dir = project_dir / ".open_edit"
    open_edit_dir.mkdir(parents=True, exist_ok=True)
    asset_store = AssetStore(open_edit_dir / "assets")
    assets = asset_store.ingest_paths([str(TESTDATA / "clip_a.mp4")])
    graph = EditGraphStore(open_edit_dir / "edit_graph.db")
    project = Project(name=name, assets={a.asset_hash: a for a in assets})
    op = AddClipOp(author="user", asset_hash=assets[0].asset_hash,
                   track_id="v1", position_sec=0.0, in_point_sec=0.0, out_point_sec=1.0)
    graph.append(op)
    project.edit_graph.append(op)
    return project_dir


def test_render_project_uses_profile_scoped_cache_key(tmp_path: Path, monkeypatch) -> None:
    from open_edit.render import orchestrator
    from open_edit.render.cache import RenderCache
    from open_edit.render.melt_runner import PipeResult

    cache_keys: list[str] = []

    def fake_get(self, key: str, ext: str = "mp4"):
        cache_keys.append(key)
        return None

    def fake_put(self, key: str, source_path):
        from pathlib import Path
        return Path(source_path)

    monkeypatch.setattr(RenderCache, "get", fake_get)
    monkeypatch.setattr(RenderCache, "put", fake_put)

    def fake_run_pipe(cmds, *, timeout_s):
        out = cmds.ffmpeg_cmd[-1]
        from pathlib import Path
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(b"MP4")
        return PipeResult(0, 0, 0, "")

    monkeypatch.setattr(orchestrator, "run_pipe", fake_run_pipe)
    monkeypatch.setattr(orchestrator.shutil, "which",
                        lambda name: "/usr/bin/melt" if name == "melt" else None)

    project_dir = _make_project(tmp_path)
    result = orchestrator.render_project(
        "proj", project_dir, tmp_path / "work", mode="final",
        quality="high", encoder_backend="cpu",
    )
    assert result.ok is True, result.error
    assert cache_keys and all("high" in k and "cpu" in k for k in cache_keys)


def test_render_project_hwaccel_retry(tmp_path: Path, monkeypatch) -> None:
    from open_edit.render import orchestrator
    from open_edit.render.melt_runner import PipeResult

    attempts: list[list[str]] = []

    def fake_run_pipe(cmds, *, timeout_s):
        attempts.append(cmds.melt_video_cmd)
        from pathlib import Path
        if len(attempts) == 1:
            return PipeResult(1, 1, 0, "melt: hwaccel exploded")
        Path(cmds.ffmpeg_cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(cmds.ffmpeg_cmd[-1]).write_bytes(b"MP4")
        return PipeResult(0, 0, 0, "")

    monkeypatch.setattr(orchestrator, "run_pipe", fake_run_pipe)
    monkeypatch.setattr(orchestrator.shutil, "which",
                        lambda name: "/usr/bin/melt" if name == "melt" else None)
    monkeypatch.setattr(orchestrator, "_gpu_decode_available", lambda: True)
    monkeypatch.setattr(orchestrator, "canonical_json_hash", lambda obj: "h1")

    project_dir = _make_project(tmp_path, name="proj2")
    result = orchestrator.render_project("proj2", project_dir, tmp_path / "work2",
                                         mode="proxy", encoder_backend="gpu")
    assert result.ok is True, result.error
    assert len(attempts) == 2  # first hwaccel attempt failed -> CPU retry
```

Note: the hwaccel probe helper `_gpu_decode_available()` is introduced in Step 3 — the tests depend on it.

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest tests/test_render/test_orchestrator.py -o addopts="" -q`
Expected: FAIL (`_gpu_decode_available` missing; old cache key behavior).

- [ ] **Step 3: Rework render_project in orchestrator.py**

Replace the body between the profile resolution and the cache/snapshot tail with the pipe path:

```python
    profile = profile_with_quality(profile_name, mode, quality, overrides)
    fingerprint = profile_fingerprint(profile, encoder_backend)
    ...
    # materialize, plan, graph_hash — unchanged (existing code) ...

    runner = MeltRunner(...)  # REMOVED — replaced by the pipe path below

    cache = RenderCache(workdir / "render_cache")
    cache_key = render_cache_key(graph_hash, fingerprint)
    if not force:
        cached = cache.get(cache_key)
        if cached and cache.is_fresh(cached):
            return RenderResult(... cache_hit=True, ...)  # existing shape

    config = EmitterConfig(profile=profile.model_dump())
    hwaccel_on = _gpu_decode_available() and resolve_backend(encoder_backend) == "gpu"
    xml = emit_timeline(plan.melt_timeline, config, asset_paths=plan.asset_paths, hwaccel=hwaccel_on)
    workdir.mkdir(parents=True, exist_ok=True)
    xml_path = workdir / f"project_{graph_hash[:12]}.mlt"
    xml_path.write_text(xml)
    output_mp4 = workdir / f"project_{graph_hash[:12]}.mp4"

    spec = resolve_encoder_args(profile, encoder_backend)
    audio_bitrate = profile.ab or ("320k" if mode == "final" else "160k")
    cmds = build_pipe_commands(
        melt_bin, xml_path, output_mp4, profile, spec, plan.overlay_clips,
        audio_bitrate=audio_bitrate, workdir=workdir,
    )
    melt_timeout = 7200 if mode == "final" else 600
    t0 = time.monotonic()
    try:
        result = run_pipe(cmds, timeout_s=melt_timeout)
    except PipeRunError as exc:
        return _fail(..., error=str(exc), record_failed_snapshot=True, ...)
    # hwaccel retry: melt failed with hwaccel XML -> re-emit without + retry once
    if result.returncode != 0 and hwaccel_on and result.melt_rc != 0:
        xml_cpu = emit_timeline(plan.melt_timeline, config, asset_paths=plan.asset_paths, hwaccel=False)
        xml_path.write_text(xml_cpu)
        try:
            result = run_pipe(cmds, timeout_s=melt_timeout)
        except PipeRunError as exc:
            return _fail(..., error=str(exc), record_failed_snapshot=True, ...)
    elapsed = time.monotonic() - t0

    if result.returncode != 0 or not output_mp4.is_file() or output_mp4.stat().st_size == 0:
        return _fail(
            mode=mode, profile=profile, output_path=str(output_mp4),
            duration_sec=timeline.duration_sec, elapsed_sec=elapsed,
            graph_hash=graph_hash,
            error=(result.stderr or f"render pipe exited {result.returncode}"),
            project_dir=project_dir, project_id=project_id, record_failed_snapshot=True,
        )

    cache.put(cache_key, output_mp4)
    record_snapshot(project_dir, project_id, graph_hash, output_mp4, success=True)
    return RenderResult(ok=True, output_path=str(output_mp4), mode=mode,
                        profile=profile.model_dump(), duration_sec=timeline.duration_sec,
                        elapsed_sec=elapsed, cache_hit=False, edit_graph_hash=graph_hash)
```

Also add the probe helper near the top of the module (module-level, memoized):

```python
_gpu_decode_ok: bool | None = None


def _gpu_decode_available() -> bool:
    """True if melt can decode with hwaccel=cuda (probed once per process)."""
    global _gpu_decode_ok
    if _gpu_decode_ok is not None:
        return _gpu_decode_ok
    import shutil as _sh
    import subprocess as _sp

    melt_bin = _sh.which("melt")
    if melt_bin is None:
        _gpu_decode_ok = False
        return False
    clip_a = Path(__file__).resolve().parents[2] / "tests" / "testdata" / "raw_videos" / "clip_a.mp4"
    probe_mlt = ("<mlt><producer id='p0'><property name='resource'>"
                 f"{clip_a}</property>"
                 "<property name='hwaccel'>cuda</property>"
                 "<property name='hwaccel_device'>0</property></producer>"
                 "<playlist id='pl'><entry producer='p0'/></playlist>"
                 "<tractor id='t0'><track producer='pl'/></tractor></mlt>")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        mlt = Path(td) / "probe.mlt"
        mlt.write_text(probe_mlt)
        proc = _sp.run([melt_bin, str(mlt), "-consumer", "null",
                        "s=64x64", "frame_rate_num=30", "frame_rate_den=1"],
                       capture_output=True, text=True, timeout=60)
        _gpu_decode_ok = proc.returncode == 0
    return _gpu_decode_ok
```

If `tests/testdata/raw_videos/clip_a.mp4` does not exist on the probe path, use a `Path(__file__).parent`-anchored path (see `tests/test_e2e_render.py` TESTDATA) so the probe is robust from any cwd.

Remove the now-unused imports (`MeltRunner`, `MeltTimeoutError`, `burn_overlays`, `GraphicsOverlayError`) and delete `open_edit/render/graphics_overlay.py`. If `tests/test_windows_mcp.py` still imports `MeltRunner.build_command`, keep `MeltRunner` in melt_runner.py (Task 2 kept it) — it is the pipe's legacy sibling and stays.

- [ ] **Step 4: Run orchestrator tests**

Run: `/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest tests/test_render/ tests/test_windows_mcp.py -o addopts="" -q`
Expected: PASS.

- [ ] **Step 5: Append the real end-to-end pipe test**

Append to `tests/test_e2e_render.py`:

```python
def test_e2e_render_quality_override_scale(tmp_path: Path) -> None:
    """Render with a scale override; verify the output resolution via ffprobe."""
    import json
    import subprocess

    project_dir = tmp_path
    open_edit_dir = project_dir / ".open_edit"
    open_edit_dir.mkdir(parents=True, exist_ok=True)
    asset_store = AssetStore(open_edit_dir / "assets")
    assets = asset_store.ingest_paths([str(TESTDATA / "clip_a.mp4")])
    graph = EditGraphStore(open_edit_dir / "edit_graph.db")
    project = Project(name="scale", assets={a.asset_hash: a for a in assets})
    op = AddClipOp(author="user", asset_hash=assets[0].asset_hash,
                   track_id="v1", position_sec=0.0, in_point_sec=0.0, out_point_sec=2.0)
    graph.append(op)
    project.edit_graph.append(op)

    result = render_project(
        project_id="scale", project_dir=project_dir,
        workdir=project_dir / "renders", mode="proxy",
        quality="fast", overrides={"scale": "320x180", "crf": 30},
    )
    assert result.ok, result.error
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", result.output_path],
        capture_output=True, text=True, check=True,
    )
    streams = json.loads(probe.stdout)["streams"]
    assert (streams[0]["width"], streams[0]["height"]) == ("320", "180")
```

- [ ] **Step 6: Run the e2e + full render suite**

Run: `/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest tests/test_e2e_render.py tests/test_render/ -o addopts="" -q`
Expected: PASS (skip_if triggers only when melt/ffmpeg missing; on this machine they exist).

- [ ] **Step 7: Full suite + lint**

Run: `/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest -o addopts="" -q tests/`
Expected: 0 failed.
Run: `/home/ah64/apps/mlt-pipeline/.venv/bin/ruff check open_edit/render/`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add -A open_edit/render tests/
git commit -m "feat(render): single-pass frame-server orchestration with hwaccel retry and profile-scoped cache"
```

---

## Task 6 (final): Verification gate

**Files:** none (verification only).

- [ ] **Step 1: Full suite**

Run: `/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest -o addopts="" -q tests/`
Expected: 0 failed, 0 errors.

- [ ] **Step 2: Layering guard + lint**

Run: `/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest tests/test_layering.py -o addopts="" -q`
and `/home/ah64/apps/mlt-pipeline/.venv/bin/ruff check open_edit/`
Expected: PASS, no errors.

- [ ] **Step 3: Manual smoke render**

Run (with a real project or the e2e fixture): `open_edit render --mode final --quality high --crf 18` on the e2e test project; verify the output file exists and plays.

- [ ] **Step 4: Update the design doc status**

Mark `Status:` line in `docs/superpowers/specs/2026-08-01-render-pipeline-fix-design.md` as `implemented`; commit.

- [ ] **Step 5: Merge gate**

After all tracks merge to `main` and Tasks 5–6 pass on `main`, regenerate the project graph:

```bash
graphify update .
```
