"""Tests for cache-aware QC policy selection."""

import pytest

from open_edit.qc.policy import (
    QCPolicy,
    qc_policy,
    resolve_qc_policy,
)


def test_proxy_warm_cache_hit_defaults_to_skip(monkeypatch) -> None:
    monkeypatch.delenv("OPEN_EDIT_PROXY_WARM_QC_MODE", raising=False)

    policy = resolve_qc_policy("proxy", cache_hit=True)

    assert policy.mode == "skip"


def test_proxy_cold_defaults_to_light(monkeypatch) -> None:
    monkeypatch.delenv("OPEN_EDIT_PROXY_QC_MODE", raising=False)

    policy = resolve_qc_policy("proxy", cache_hit=False)

    assert policy.mode == "light"


def test_final_policy_is_full_and_duration_budgeted() -> None:
    policy = resolve_qc_policy("final", cache_hit=True)

    assert policy.mode == "full"
    assert policy.blackdetect_timeout(180.0) == pytest.approx(135.0)
    assert policy.blackdetect_timeout(3600.0) == 900.0


def test_blackdetect_timeout_has_safe_floor_and_cap() -> None:
    policy = QCPolicy("full", None, 45.0)

    assert policy.blackdetect_timeout(None) == 45.0
    assert policy.blackdetect_timeout(0.0) == 45.0
    assert policy.blackdetect_timeout(10.0) == 60.0


def test_proxy_policy_modes_can_be_overridden(monkeypatch) -> None:
    monkeypatch.setenv("OPEN_EDIT_PROXY_QC_MODE", "full")
    assert resolve_qc_policy("proxy", cache_hit=False).mode == "full"

    monkeypatch.setenv("OPEN_EDIT_PROXY_WARM_QC_MODE", "light")
    assert resolve_qc_policy("proxy", cache_hit=True).mode == "light"


def test_proxy_cache_hit_skips_qc_by_default(monkeypatch):
    monkeypatch.delenv("OPEN_EDIT_PROXY_QC_POLICY", raising=False)

    assert qc_policy("proxy", cache_hit=True) == "skip"
    assert qc_policy("proxy", cache_hit=False) == "run"


def test_final_and_overlay_always_run_qc():
    assert qc_policy("final", cache_hit=True) == "run"
    assert qc_policy("overlay", cache_hit=True) == "run"


def test_proxy_policy_can_force_always(monkeypatch):
    monkeypatch.setenv("OPEN_EDIT_PROXY_QC_POLICY", "always")

    assert qc_policy("proxy", cache_hit=True) == "run"
    assert qc_policy("proxy", cache_hit=False) == "run"


def test_proxy_policy_can_force_never(monkeypatch):
    monkeypatch.setenv("OPEN_EDIT_PROXY_QC_POLICY", "never")

    assert qc_policy("proxy", cache_hit=True) == "skip"
    assert qc_policy("proxy", cache_hit=False) == "skip"
