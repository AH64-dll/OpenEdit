"""Tests for cache-aware QC policy selection."""

from open_edit.qc.policy import qc_policy


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
