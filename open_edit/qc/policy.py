"""Deterministic policy for deciding whether render QC should run."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from open_edit.qc.gate import QCReport

QCMode = Literal["skip", "light", "full"]
QCDecision = Literal["run", "skip"]

PROXY_QC_POLICY_ENV = "OPEN_EDIT_PROXY_QC_POLICY"
DEFAULT_PROXY_QC_POLICY = "skip_on_hit"
_PROXY_QC_POLICIES = frozenset({"always", DEFAULT_PROXY_QC_POLICY, "never"})

PROXY_QC_MODE_ENV = "OPEN_EDIT_PROXY_QC_MODE"
PROXY_WARM_QC_MODE_ENV = "OPEN_EDIT_PROXY_WARM_QC_MODE"
FINAL_QC_BUDGET_ENV = "OPEN_EDIT_FINAL_QC_BUDGET_SEC"
BLACKDETECT_MAX_ENV = "OPEN_EDIT_QC_BLACKDETECT_MAX_SEC"

DEFAULT_PROXY_QC_MODE: QCMode = "light"
DEFAULT_WARM_PROXY_QC_MODE: QCMode = "skip"
DEFAULT_FINAL_QC_BUDGET_SEC = 900.0
DEFAULT_BLACKDETECT_MAX_SEC = 900.0

QC_CHECK_NAMES: tuple[str, ...] = (
    "render_completed",
    "proxy_render",
    "streams",
    "duration",
    "audio_sync",
    "black_frames",
    "frozen_frames",
    "silence",
    "overlays_burned",
    "thumbnail",
)


@dataclass(frozen=True)
class QCPolicy:
    """Resolved QC work and timeout budget for one render."""

    mode: QCMode
    total_budget_sec: float | None
    blackdetect_max_sec: float

    def blackdetect_timeout(self, duration_sec: float | None) -> float:
        """Return a duration-aware timeout for ffmpeg blackdetect."""
        if duration_sec is None or duration_sec <= 0:
            return min(60.0, self.blackdetect_max_sec)
        return max(
            60.0,
            min(self.blackdetect_max_sec, duration_sec * 0.75),
        )


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if math.isfinite(value) and value > 0 else default


def _env_mode(name: str, default: QCMode) -> QCMode:
    value = os.environ.get(name, "").strip().lower()
    if value in {"skip", "light", "full"}:
        return value  # type: ignore[return-value]
    return default


def resolve_qc_policy(
    render_mode: str | None,
    *,
    cache_hit: bool,
) -> QCPolicy:
    """Resolve proxy warm/cold and final policy from mode plus environment."""
    normalized_mode = (render_mode or "").strip().lower()
    blackdetect_max = _env_float(
        BLACKDETECT_MAX_ENV, DEFAULT_BLACKDETECT_MAX_SEC,
    )
    final_budget = _env_float(
        FINAL_QC_BUDGET_ENV, DEFAULT_FINAL_QC_BUDGET_SEC,
    )

    # Keep the M1 variable meaningful for operators who already configured it.
    # Its absence is intentionally not treated as ``skip_on_hit``: M2's new
    # cold-proxy default is the lighter policy.
    legacy_configured = os.environ.get(PROXY_QC_POLICY_ENV)
    if normalized_mode == "proxy" and legacy_configured is not None:
        legacy = legacy_configured.strip().lower()
        if legacy == "never":
            return QCPolicy("skip", None, blackdetect_max)
        if legacy == "always":
            return QCPolicy("full", None, blackdetect_max)
        if legacy == DEFAULT_PROXY_QC_POLICY:
            mode: QCMode = "skip" if cache_hit else "full"
            return QCPolicy(mode, None, blackdetect_max)

    if normalized_mode == "proxy":
        mode = _env_mode(
            PROXY_WARM_QC_MODE_ENV if cache_hit else PROXY_QC_MODE_ENV,
            DEFAULT_WARM_PROXY_QC_MODE if cache_hit else DEFAULT_PROXY_QC_MODE,
        )
        return QCPolicy(mode, None, blackdetect_max)

    if normalized_mode in {"final", "overlay"}:
        return QCPolicy("full", final_budget, blackdetect_max)

    return QCPolicy("full", None, blackdetect_max)


def skipped_qc_report(
    video_path: str,
    *,
    policy: QCPolicy,
    reason: str,
) -> "QCReport":
    """Return a stable, explicit report without decoding the whole video."""
    # Import lazily to avoid the policy ↔ gate import cycle.
    from open_edit.qc.gate import QCCheck, QCReport

    detail = f"skipped by policy={policy.mode}; {reason}"
    checks = [
        QCCheck(name=name, passed=True, skipped=True, detail=detail)
        for name in QC_CHECK_NAMES
    ]
    # Keep the path in a diagnostic detail without probing or decoding it.
    checks[1].detail = f"{detail}; output={video_path}"
    return QCReport(
        passed=True,
        checks=checks,
        policy=policy.mode,
        complete=False,
        reason=reason,
    )


def qc_policy(mode: str | None, *, cache_hit: bool) -> QCDecision:
    """Return whether QC should run for a rendered deliverable.

    Final and overlay renders always run QC. Proxy renders default to running
    QC on cold renders and skipping it for verified cache hits. The proxy
    behavior can be overridden with ``always`` or ``never`` through
    ``OPEN_EDIT_PROXY_QC_POLICY``.
    """
    normalized_mode = (mode or "").strip().lower()
    if normalized_mode in {"final", "overlay"}:
        return "run"
    if normalized_mode != "proxy":
        return "run"

    configured = (
        os.environ.get(PROXY_QC_POLICY_ENV, DEFAULT_PROXY_QC_POLICY)
        .strip()
        .lower()
    )
    if configured not in _PROXY_QC_POLICIES:
        configured = DEFAULT_PROXY_QC_POLICY

    if configured == "always":
        return "run"
    if configured == "never":
        return "skip"
    return "skip" if cache_hit else "run"
