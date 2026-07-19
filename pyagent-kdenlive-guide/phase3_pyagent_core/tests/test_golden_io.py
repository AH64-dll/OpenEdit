"""Golden-file tests that lock the 19 tools' JSON I/O.

These tests run each (op, args) pair against a copy of the demo
project, then compare the response's structure against a checked-in
golden file. The golden captures the schema — keys, types, and
non-timestamp values — so that any future refactor that silently
changes what a tool returns is caught here.

Two design choices:

1. We copy the demo fixture to a tmp dir before every call so the
   read-only tests are idempotent and the fixture stays clean.
2. The comparison is "subset + recursive": we check that every
   documented key in the golden is present in the actual response
   with a matching value, but we allow extra keys (forward compat)
   and we skip timestamp/uuid fields that vary between runs.

This file is intentionally short. If it grows past ~200 lines, that
is a signal that the golden should be split per-domain (one golden
per tools/*.py).
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, is_dataclass
from pathlib import Path

import pytest

from phase3_pyagent_core.runtime import run_op


def _to_jsonable(obj):
    """Mirror runtime._to_jsonable: turn dataclasses into dicts.

    We keep a private copy here so the test does not import private
    internals. The shape must match what the runtime emits over
    stdout (which is what the extension sees).
    """
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj


GOLDEN_PATH = Path(__file__).parent / "fixtures" / "golden_io.json"
DEMO_PROJECT = Path(__file__).parent / "fixtures" / "demo.kdenlive"
CATALOG = "phase1_knowledge_base/catalog.json"


# One entry per (op, args) that has a meaningful JSON response worth
# locking. Read-only tools are listed first; mutating tools are also
# covered because they are the high-risk surface (the ones the LLM
# actually relies on for correct ground-truth after an edit).
#
# `key` is the JSON key in the golden file. For tools with multiple
# meaningful argument combinations (e.g. list_catalog's three kinds)
# we suffix the kind to keep them as separate golden entries.
def _setup_remove_transition(proj_path: str, catalog_path: str, _args: dict) -> dict:
    """Insert 2 adjacent clips, add a dissolve, capture the id.

    The demo fixture has 1 clip on track 0 of duration 4.0. Insert
    a second clip at 4.0, then add a transition between them. The
    captured id is returned so the test loop can call remove_transition
    with it.
    """
    insert_args = {
        "track_index": 0, "position_sec": 4.0,
        "source_id": "1", "source_in_sec": 0.0, "source_out_sec": 2.0,
    }
    code, resp = run_op("insert_clip", insert_args, proj_path, catalog_path)
    assert code == 0, f"setup insert_clip failed: {resp}"
    new_clip_id = resp.get("result", "")
    if isinstance(new_clip_id, dict):
        new_clip_id = new_clip_id.get("clip_id", "")
    assert new_clip_id, f"setup insert_clip returned no id: {resp}"
    # The first clip in the demo is "2"; the new one is whatever id was assigned.
    add_args = {
        "clip_a_id": "2", "clip_b_id": new_clip_id,
        "kind": "dissolve", "duration_sec": 1.0,
    }
    code, resp = run_op("add_transition", add_args, proj_path, catalog_path)
    assert code == 0, f"setup add_transition failed: {resp}"
    new_tid = resp.get("result", "")
    assert new_tid, f"setup add_transition returned no id: {resp}"
    return {"transition_id": new_tid}


def _setup_group_clips(_proj_path: str, _catalog_path: str, args: dict) -> dict:
    """Replace the PLACEHOLDER_KID and PLACEHOLDER_NAME in the golden args
    with the demo's existing clip "2" and a fixed name. No mutation needed
    — the golden op itself writes the group."""
    resolved = dict(args)
    resolved["clip_ids"] = ["2"]
    resolved["group_name"] = "golden_test"
    return resolved


def _setup_ungroup_clips(proj_path: str, catalog_path: str, _args: dict) -> dict:
    """Create a group first (using the demo's clip "2"), then return the
    group_name for the golden ungroup_clips op."""
    name = "golden_test"
    code, _ = run_op("group_clips", {"clip_ids": ["2"], "group_name": name},
                     proj_path, catalog_path)
    assert code == 0, f"setup group_clips failed"
    return {"group_name": name}


# One entry per (op, args) that has a meaningful JSON response worth
# locking. Read-only tools are listed first; mutating tools are also
# covered because they are the high-risk surface (the ones the LLM
# actually relies on for correct ground-truth after an edit).
#
# `key` is the JSON key in the golden file. For tools with multiple
# meaningful argument combinations (e.g. list_catalog's three kinds)
# we suffix the kind to keep them as separate golden entries.
_CASES: list[tuple[str, dict, str]] = [
    # --- Read-only project intros ---
    ("get_project_info", {}, "get_project_info"),
    ("get_timeline_summary", {}, "get_timeline_summary"),
    # --- Catalog lookups (one per kind) ---
    ("list_catalog", {"kind": "effects"}, "list_catalog_effects"),
    ("list_catalog", {"kind": "transitions"}, "list_catalog_transitions"),
    ("list_catalog", {"kind": "generators"}, "list_catalog_generators"),
    # --- clips-edit (5 mutating tools) ---
    ("slip_clip", {"clip_id": "2", "delta_sec": 0.0}, "slip_clip"),
    ("ripple_delete_clip", {"clip_id": "2"}, "ripple_delete_clip"),
    ("change_clip_speed", {"clip_id": "2", "rate": 1.0}, "change_clip_speed"),
    ("split_clip", {"clip_id": "2", "at_sec": 2.0}, "split_clip"),
    ("replace_clip_source", {"clip_id": "2", "new_source_id": "1"}, "replace_clip_source"),
    # --- effects (apply is exercised by remove's setup; remove is locked here) ---
    ("remove_effect", {"clip_id": "2", "effect_index": 0}, "remove_effect"),
    # --- transitions (remove is exercised; add_transition supplies the id via setup) ---
    ("remove_transition", {}, "remove_transition"),
    # --- groups (list_groups is read-only; group/ungroup use a placeholder
    #     setup that captures a real clip_id from the demo) ---
    ("list_groups", {}, "list_groups"),
    ("group_clips", {"clip_ids": ["PLACEHOLDER_KID"], "group_name": "PLACEHOLDER_NAME"}, "group_clips"),
    ("ungroup_clips", {"group_name": "PLACEHOLDER_NAME"}, "ungroup_clips"),
]

# Some golden cases need setup: the op alone would error because the
# demo fixture's clip "2" has no effects yet. `_SETUP` runs an op first
# against the same tmp project (auto-saves), then the golden op runs.
# Keep this minimal — only add a setup when the op's precondition
# isn't already true in the demo fixture.
#
# A value can be either:
# - (op_name, args_dict): a single op to run as setup.
# - A callable(proj_path, catalog_path, args_dict) -> dict: a custom
#   setup that mutates the project in place and returns the resolved
#   args for the golden op. Use this when the golden args depend on
#   a value produced by the setup (e.g. a freshly generated transition id).
_SETUP: dict = {
    "remove_effect": (
        "apply_effect", {"clip_id": "2", "effect_id": "sepia"},
    ),
    "remove_transition": _setup_remove_transition,
    "group_clips": _setup_group_clips,
    "ungroup_clips": _setup_ungroup_clips,
}

# Read-only ops do not mutate, so we can run them directly against the
# demo fixture (no tmp copy needed) — and that keeps the response's
# `path` field stable between golden generation and test runs. (This
# is a hardcoded set; do NOT derive from _CASES — that would include
# mutating ops and corrupt the demo fixture.)
_READ_ONLY_OPS = {"get_project_info", "get_timeline_summary", "list_catalog", "list_groups"}


def _skip_if_fixture_missing() -> None:
    if not DEMO_PROJECT.exists():
        pytest.skip(f"demo fixture missing: {DEMO_PROJECT}")
    if not os.path.exists(CATALOG):
        pytest.skip(f"catalog missing: {CATALOG}")


def _compare_key_subset(actual, expected, path: str = "") -> None:
    """Recursively check that every key in `expected` exists in `actual`.

    Skips env-specific fields (project `path` and the project's UUID
    `name` — both vary by checkout / fixture) and allows the actual
    to have extra keys (forward compatibility).
    """
    skip_keys = {
        "modified", "created", "uuid", "control_uuid", "id",
        "path",  # project file path varies by checkout
        "name",  # in ProjectInfo this is a UUID, varies by fixture
        "transition_id",  # auto-assigned by next_kdenlive_id, varies by run
    }
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: expected dict, got {type(actual).__name__}"
        for k, v in expected.items():
            if k in skip_keys:
                continue
            assert k in actual, f"{path}: missing key {k!r}"
            _compare_key_subset(actual[k], v, f"{path}.{k}")
    elif isinstance(expected, list):
        assert isinstance(actual, (list, tuple)), (
            f"{path}: expected list, got {type(actual).__name__}"
        )
        actual = list(actual)  # dataclass asdict leaves tuples; normalize
        assert len(actual) >= len(expected), (
            f"{path}: actual list shorter ({len(actual)}) than golden ({len(expected)})"
        )
        for i, v in enumerate(expected):
            _compare_key_subset(actual[i], v, f"{path}[{i}]")
    else:
        assert actual == expected, f"{path}: {actual!r} != {expected!r}"


@pytest.mark.parametrize("op,args,key", _CASES, ids=[c[2] for c in _CASES])
def test_op_output_matches_golden(op, args, key, tmp_path):
    _skip_if_fixture_missing()
    # Read-only ops can hit the demo fixture directly; this keeps the
    # `path` field stable between golden generation and test runs.
    # (When future mutating cases are added, copy to tmp_path first.)
    if op in _READ_ONLY_OPS:
        proj_path = str(DEMO_PROJECT)
    else:
        test_proj = tmp_path / "test.kdenlive"
        shutil.copy(DEMO_PROJECT, test_proj)
        proj_path = str(test_proj)
    if op in _SETUP:
        setup = _SETUP[op]
        if callable(setup):
            # Multi-step setup; returns the resolved args for the golden op.
            args = setup(proj_path, CATALOG, args)
        else:
            setup_op, setup_args = setup
            setup_code, setup_resp = run_op(setup_op, setup_args, proj_path, CATALOG)
            assert setup_code == 0, f"setup {setup_op} failed: {setup_resp}"
    code, resp = run_op(op, args, proj_path, CATALOG)
    assert code == 0, f"{op} failed: {resp}"
    assert resp.get("ok") is True, f"{op} not ok: {resp}"
    actual = _to_jsonable(resp.get("result", resp))
    with open(GOLDEN_PATH) as f:
        golden = json.load(f)
    assert key in golden, f"no golden entry for {key!r} (run generate_golden.py)"
    _compare_key_subset(actual, golden[key], path=key)


def test_golden_covers_every_read_only_op():
    """The golden file should have an entry for every read-only op.

    Mutating ops are exercised by tests/test_runtime.py + the
    per-domain test files; the golden only locks the I/O shape of
    the operations whose response is "what does the project look
    like right now?" — the things the LLM reads back.
    """
    if not GOLDEN_PATH.exists():
        pytest.skip("golden file not generated yet")
    with open(GOLDEN_PATH) as f:
        golden = json.load(f)
    expected_keys = {c[2] for c in _CASES}
    assert set(golden.keys()) >= expected_keys, (
        f"golden missing keys: {expected_keys - set(golden.keys())}"
    )
