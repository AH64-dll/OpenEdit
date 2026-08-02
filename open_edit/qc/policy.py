"""Deterministic policy for deciding whether render QC should run."""

from __future__ import annotations

import os
from typing import Literal

QCDecision = Literal["run", "skip"]

PROXY_QC_POLICY_ENV = "OPEN_EDIT_PROXY_QC_POLICY"
DEFAULT_PROXY_QC_POLICY = "skip_on_hit"
_PROXY_QC_POLICIES = frozenset({"always", DEFAULT_PROXY_QC_POLICY, "never"})


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
