"""Regression tests for the per-graph AAC audio cache.

The wav mix depends only on the edit-graph hash; encoding it to AAC once per
graph and muxing with ``-c:a copy`` afterwards cuts ~28-40s out of every
non-cached render (native AAC twoloop was ~40s; fast coder ~12s once).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from open_edit.render.orchestrator import encode_audio_aac_cache

ffmpeg = pytest.importorskip("shutil").which("ffmpeg") if False else None


def _make_wav(path: Path, seconds: float = 2.0) -> None:
    """Synthesize a tiny stereo wav with ffmpeg."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
            "-f", "lavfi", "-i", f"sine=frequency=550:duration={seconds}",
            "-filter_complex", "[0:a][1:a]amerge=inputs=2[a]",
            "-map", "[a]", "-ac", "2", "-ar", "48000", str(path),
        ],
        check=True, capture_output=True,
    )


def test_encode_aac_cache_creates_file(tmp_path: Path) -> None:
    if subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0:
        pytest.skip("ffmpeg not on PATH")
    wav = tmp_path / "mix.wav"
    aac = tmp_path / "mix.m4a"
    _make_wav(wav)
    assert encode_audio_aac_cache(wav, aac, bitrate="96k") is True
    assert aac.is_file() and aac.stat().st_size > 0
    # Idempotent: existing cache file -> immediate True, file untouched.
    before = aac.stat().st_mtime_ns
    assert encode_audio_aac_cache(wav, aac, bitrate="96k") is True
    assert aac.stat().st_mtime_ns == before


def test_encode_aac_cache_missing_wav(tmp_path: Path) -> None:
    assert encode_audio_aac_cache(tmp_path / "nope.wav", tmp_path / "nope.m4a") is False


def test_encode_aac_cache_invalid_wav(tmp_path: Path) -> None:
    bogus = tmp_path / "bogus.wav"
    bogus.write_bytes(b"not audio at all")
    assert encode_audio_aac_cache(bogus, tmp_path / "bogus.m4a") is False
