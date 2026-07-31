"""Sandbox package: backends, staging, bootstrap codegen, and facades.

Split from the former single-module sandbox bridge (Task 5.4):

- ``backends``: SandboxBackend ABC + BwrapBackend + DevSubprocessBackend +
  backend selection + binary resolution.
- ``staging``: shared stage / collect / cleanup (``stage_and_collect``).
- ``bootstrap``: ``render_bootstrap`` codegen for in-sandbox execution.
- ``bridge``: ``run_free_form`` / ``run_render`` facades.

This module re-exports the public API for importers of the old module:
``run_free_form``, ``run_render``, ``SandboxUnavailable``.
"""
from open_edit.agent.sandbox.backends import (
    BwrapBackend,
    DevSubprocessBackend,
    SandboxBackend,
    SandboxUnavailable,
    get_sandbox_backend,
)
from open_edit.agent.sandbox.bridge import run_free_form, run_render

__all__ = [
    "BwrapBackend",
    "DevSubprocessBackend",
    "SandboxBackend",
    "SandboxUnavailable",
    "get_sandbox_backend",
    "run_free_form",
    "run_render",
]
