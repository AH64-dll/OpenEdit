"""Auto color grading for OpenEdit.

Ported from browser-use/video-use ``helpers/grade.py`` (MIT) and adapted to
OpenEdit's IR effect model: instead of returning an ffmpeg filter string, the
analyzer returns per-axis ``eq`` parameters (contrast/gamma/saturation) that
map 1:1 onto the ``color_grade`` catalog effect (MLT ``avfilter.eq``).

Semantics preserved from video-use:

- Auto mode samples ~10 frames of the exact clip range via ffmpeg
  ``signalstats`` + ``metadata=print`` (bit-depth normalized to 0..1), then
  emits a *bounded* correction: contrast boost if flat, gamma lift if dark,
  tiny saturation pullback by default. All axes clamped to +/-8%.
- Presets: ``subtle`` (safe floor), ``neutral_punch`` (eq + S-curve),
  ``warm_cinematic`` (opt-in creative), ``none`` (skip grading).
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

# eq-compatible component of each preset (contrast/gamma/saturation only).
# Creative components (curves / colorbalance) are exposed separately as the
# ``grade_curves`` / ``grade_colorbalance`` effects so they stay composable.
PRESET_EQ_PARAMS: dict[str, dict[str, float]] = {
    "subtle": {"contrast": 1.03, "gamma": 1.0, "saturation": 0.98},
    "neutral_punch": {"contrast": 1.06, "gamma": 1.0, "saturation": 1.0},
    "warm_cinematic": {"contrast": 1.12, "gamma": 1.0, "saturation": 0.88},
    "none": {},
}

PRESET_CURVES: dict[str, str | None] = {
    "subtle": None,
    "neutral_punch": "0/0 0.25/0.23 0.75/0.77 1/1",
    "warm_cinematic": "0/0 0.25/0.22 0.75/0.78 1/1",
    "none": None,
}

# warm_cinematic colorbalance (teal shadows / warm highlights), keyed by the
# ffmpeg colorbalance option names (rs=shadows red ... bh=highlights blue).
PRESET_COLORBALANCE: dict[str, dict[str, float] | None] = {
    "subtle": None,
    "neutral_punch": None,
    "warm_cinematic": {
        "rs": 0.02, "gs": 0.0, "bs": -0.03,
        "rm": 0.04, "gm": 0.01, "bm": -0.02,
        "rh": 0.08, "gh": 0.02, "bh": -0.05,
    },
    "none": None,
}


def known_presets() -> list[str]:
    return sorted(PRESET_EQ_PARAMS)


def _sample_frame_stats(
    video: Path,
    start: float,
    duration: float,
    n_samples: int = 10,
) -> dict[str, float]:
    """Sample N frames from a range and compute brightness/contrast stats.

    Uses ffmpeg ``signalstats`` (YMIN/YMAX/YAVG/SATAVG) via metadata=print and
    normalizes by native bit depth so all values live in 0..1.
    """
    fps = max(0.5, min(n_samples / max(duration, 0.1), 10.0))

    with tempfile.NamedTemporaryFile(mode="w+", suffix=".txt", delete=False) as f:
        metadata_path = f.name

    try:
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-nostats",
            "-ss", f"{start:.3f}",
            "-i", str(video),
            "-t", f"{duration:.3f}",
            "-vf", f"fps={fps:.2f},signalstats,metadata=print:file={metadata_path}",
            "-f", "null", "-",
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        y_avgs: list[float] = []
        y_mins: list[float] = []
        y_maxs: list[float] = []
        sat_avgs: list[float] = []
        bit_depth: int = 8

        def _parse_value(line: str) -> float | None:
            try:
                return float(line.rsplit("=", 1)[1])
            except (ValueError, IndexError):
                return None

        with open(metadata_path) as f:
            for line in f:
                line = line.strip()
                if "lavfi.signalstats.YBITDEPTH" in line:
                    v = _parse_value(line)
                    if v is not None:
                        bit_depth = int(v)
                elif "lavfi.signalstats.YAVG" in line:
                    v = _parse_value(line)
                    if v is not None:
                        y_avgs.append(v)
                elif "lavfi.signalstats.YMIN" in line:
                    v = _parse_value(line)
                    if v is not None:
                        y_mins.append(v)
                elif "lavfi.signalstats.YMAX" in line:
                    v = _parse_value(line)
                    if v is not None:
                        y_maxs.append(v)
                elif "lavfi.signalstats.SATAVG" in line:
                    v = _parse_value(line)
                    if v is not None:
                        sat_avgs.append(v)

        if not y_avgs:
            # Analysis failed — return neutral defaults (no correction)
            return {"y_mean": 0.5, "y_std": 0.18, "sat_mean": 0.25}

        max_val = (2 ** bit_depth) - 1

        y_mean = (sum(y_avgs) / len(y_avgs)) / max_val
        y_range = (
            ((sum(y_maxs) / len(y_maxs)) - (sum(y_mins) / len(y_mins))) / max_val
            if y_maxs and y_mins
            else 0.7
        )
        sat_mean = ((sum(sat_avgs) / len(sat_avgs)) / max_val) if sat_avgs else 0.25

        return {
            "y_mean": y_mean,
            "y_std": y_range / 4.0,
            "sat_mean": sat_mean,
        }
    finally:
        Path(metadata_path).unlink(missing_ok=True)


def _probe_duration(video: Path) -> float:
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video),
        ]).decode().strip()
        return float(out)
    except Exception:
        return 10.0


def auto_grade_params(
    video: Path,
    start: float = 0.0,
    duration: float | None = None,
) -> dict[str, float]:
    """Analyze a clip range and return bounded eq params (contrast/gamma/saturation).

    Mirrors video-use ``auto_grade_for_clip`` decision rules exactly:
    contrast target y_range ~= 0.72, gamma target y_mean ~= 0.48,
    saturation target ~= 0.25, all clamped to +/-8%.
    """
    if duration is None:
        duration = _probe_duration(video)

    stats = _sample_frame_stats(video, start, duration)

    y_mean = stats["y_mean"]
    y_range = stats["y_std"] * 4.0
    sat_mean = stats["sat_mean"]

    contrast_adj = 1.0
    if y_range < 0.65:
        t = max(0.0, min(1.0, (y_range - 0.50) / 0.15))
        contrast_adj = 1.08 - 0.05 * t
    else:
        contrast_adj = 1.03

    gamma_adj = 1.0
    if y_mean < 0.42:
        t = max(0.0, min(1.0, (y_mean - 0.30) / 0.12))
        gamma_adj = 1.10 - 0.08 * t
    elif y_mean > 0.60:
        gamma_adj = 0.97

    sat_adj = 0.98
    if sat_mean < 0.18:
        sat_adj = 1.04
    elif sat_mean > 0.38:
        sat_adj = 0.96

    return {
        "contrast": round(max(0.94, min(1.08, contrast_adj)), 3),
        "gamma": round(max(0.94, min(1.10, gamma_adj)), 3),
        "saturation": round(max(0.94, min(1.06, sat_adj)), 3),
    }


def preset_eq_params(name: str) -> dict[str, float]:
    """Return eq params for a named preset; raises KeyError for unknown names."""
    if name not in PRESET_EQ_PARAMS:
        raise KeyError(f"unknown preset {name!r}. Available: {', '.join(known_presets())}")
    return dict(PRESET_EQ_PARAMS[name])
