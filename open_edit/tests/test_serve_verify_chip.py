"""v1.5: tests for the verification chip in the chat UI.

A small chip near the chat-status pill that surfaces the visual-verify
stage progress: "Checking render 1/3…", "Render verified", "Render
failed verification", "Verification skipped", "Render loop capped".
Hidden when idle.

States: ``idle`` | ``checking`` | ``verified`` | ``failed`` | ``skipped``
| ``capped``. The chip is driven by the ``verification_started`` and
``verification_result`` WS events the v1.5 agent loop emits, and resets
to ``idle`` on ``done`` and ``error`` so a fresh turn starts clean.

Mirrors the structure of ``test_serve_chat_status.py`` and
``test_serve_cost_badge.py`` — the chip is a factory function
(``createVerifyChip(element)``) and the tests drive it via the
Node-sandbox harness with a stub DOM. We import ``chat.js`` directly in
the test body (the harness still loads ``app.js`` so the browser-like
globals are present) so the chip is testable without expanding the
``__testHooks`` surface in ``app.js``.

Spec: docs/superpowers/specs/2026-07-21-visual-verify-design.md §5
(WS protocol) + §9 (Components — frontend section).
Plan: docs/superpowers/plans/2026-07-21-v1.5-visual-verify.md (Task 4).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _node_harness import (  # noqa: E402
    app_js_path,
    harness as _harness,
    run_node_script as _run_node_script,
)

APP_JS = app_js_path()
assert APP_JS.exists(), f"missing {APP_JS}"

# Resolve chat.js once so each test points at the same file.
CHAT_JS = APP_JS.parent / "js" / "chat.js"
assert CHAT_JS.exists(), f"missing {CHAT_JS}"


# ---------------------------------------------------------------------------
# Shared harness body — wraps a sync test driver in an async IIFE that
# imports chat.js so ``createVerifyChip`` is reachable. Keeps the test
# bodies below declarative: each test supplies a JS snippet that
# receives the chip + stub and returns a JSON-serialisable result.
# ---------------------------------------------------------------------------

_HARNESS_PREFIX = r"""
'use strict';
const { pathToFileURL } = require('url');
const path = require('path');
const appPath = path.resolve(process.argv[2]);
const chatPath = path.resolve(path.dirname(appPath), 'js/chat.js');
const chat = await import(pathToFileURL(chatPath).href);
globalThis.__verifyChipFactory = chat.createVerifyChip;
"""


def _run(script_body: str) -> tuple[int, str, str]:
    """Run ``script_body`` (JS) through the harness and return the
    ``(returncode, stdout, stderr)`` triple."""
    full = _HARNESS_PREFIX + script_body
    wrapped = _harness(full)
    return _run_node_script(wrapped, APP_JS)


# ---------------------------------------------------------------------------
# 1. chip starts hidden
# ---------------------------------------------------------------------------

def test_chip_starts_hidden():
    """A fresh chip must start in the ``idle`` state with the ``hidden``
    class applied — the chip should not be visible until the first
    ``verification_started`` event arrives."""
    rc, out, err = _run(r"""
const stubs = globalThis.__verifyChipFactory;
const textHistory = [];
const dataStateHistory = [];
const classesAdded = new Set();
const classesRemoved = new Set();
const stubEl = {
  classList: {
    add: (c) => classesAdded.add(c),
    remove: (c) => classesRemoved.add(c),
    toggle: () => {},
  },
  setAttribute: (k, v) => { if (k === 'data-state') dataStateHistory.push(v); },
  querySelector: (sel) => {
    if (sel === '.verify-chip-text') {
      return {
        get textContent() { return textHistory[textHistory.length - 1] || ''; },
        set textContent(v) { textHistory.push(v); },
      };
    }
    return { textContent: '' };
  },
};
const chip = stubs(stubEl);
console.log(JSON.stringify({
  state: chip.getState().state,
  dataState: dataStateHistory[dataStateHistory.length - 1],
  hiddenAdded: classesAdded.has('hidden'),
  hiddenRemoved: classesRemoved.has('hidden'),
  label: textHistory[textHistory.length - 1] || '',
}));
""")
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    info = json.loads(out.strip().splitlines()[-1])
    assert info["state"] == "idle", f"chip should start in idle, got {info!r}"
    assert info["dataState"] == "idle", (
        f"data-state should be 'idle' on construction, got {info['dataState']!r}"
    )
    assert info["hiddenAdded"] is True, (
        f"chip should add 'hidden' class on construction so it doesn't "
        f"show before the first verification_started event, got {info!r}"
    )
    assert info["hiddenRemoved"] is False, (
        f"chip must NOT remove 'hidden' during idle init, got {info!r}"
    )
    assert info["label"] == "", (
        f"label should be empty in idle state, got {info['label']!r}"
    )


# ---------------------------------------------------------------------------
# 2. verification_started → "Checking render N/M…"
# ---------------------------------------------------------------------------

def test_verification_started_shows_checking_label():
    """On a ``verification_started`` event the chip should drop the
    ``hidden`` class and render a "Checking render N/M…" label. The
    render count is bumped from the current counter."""
    rc, out, err = _run(r"""
const stubs = globalThis.__verifyChipFactory;
const textHistory = [];
const dataStateHistory = [];
const classesAdded = new Set();
const classesRemoved = new Set();
const stubEl = {
  classList: {
    add: (c) => classesAdded.add(c),
    remove: (c) => classesRemoved.add(c),
    toggle: () => {},
  },
  setAttribute: (k, v) => { if (k === 'data-state') dataStateHistory.push(v); },
  querySelector: (sel) => {
    if (sel === '.verify-chip-text') {
      return {
        get textContent() { return textHistory[textHistory.length - 1] || ''; },
        set textContent(v) { textHistory.push(v); },
      };
    }
    return { textContent: '' };
  },
};
const chip = stubs(stubEl);
chip.onEvent({
  type: 'verification_started',
  render_id: 'r1',
  frame_count: 3,
  stage: 'sampling',
});
console.log(JSON.stringify({
  state: chip.getState().state,
  dataState: dataStateHistory[dataStateHistory.length - 1],
  hiddenAdded: classesAdded.has('hidden'),
  hiddenRemoved: classesRemoved.has('hidden'),
  label: textHistory[textHistory.length - 1] || '',
}));
""")
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    info = json.loads(out.strip().splitlines()[-1])
    assert info["state"] == "checking", info
    assert info["dataState"] == "checking", (
        f"data-state should be 'checking' after verification_started, got {info!r}"
    )
    assert info["hiddenRemoved"] is True, (
        f"chip should drop 'hidden' when verification starts, got {info!r}"
    )
    assert "Checking render" in info["label"], (
        f"label should say 'Checking render …', got {info['label']!r}"
    )


# ---------------------------------------------------------------------------
# 3. verification_result pass → verified
# ---------------------------------------------------------------------------

def test_verification_result_pass_shows_verified():
    """``outcome=pass`` is the happy path: chip transitions to
    ``verified`` (green). The label should reflect that the render
    was verified."""
    rc, out, err = _run(r"""
const stubs = globalThis.__verifyChipFactory;
const textHistory = [];
const dataStateHistory = [];
const stubEl = {
  classList: { add: () => {}, remove: () => {}, toggle: () => {} },
  setAttribute: (k, v) => { if (k === 'data-state') dataStateHistory.push(v); },
  querySelector: (sel) => {
    if (sel === '.verify-chip-text') {
      return {
        get textContent() { return textHistory[textHistory.length - 1] || ''; },
        set textContent(v) { textHistory.push(v); },
      };
    }
    return { textContent: '' };
  },
};
const chip = stubs(stubEl);
chip.onEvent({ type: 'verification_started', render_id: 'r1', frame_count: 1, stage: 'ready' });
chip.onEvent({
  type: 'verification_result',
  render_id: 'r1',
  outcome: 'pass',
  verdict_source: 'model_explicit_pass',
  render_count: 1,
  max_renders: 3,
});
console.log(JSON.stringify({
  state: chip.getState().state,
  dataState: dataStateHistory[dataStateHistory.length - 1],
  label: textHistory[textHistory.length - 1] || '',
}));
""")
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    info = json.loads(out.strip().splitlines()[-1])
    assert info["state"] == "verified", info
    assert info["dataState"] == "verified", (
        f"data-state should be 'verified' on pass, got {info!r}"
    )
    assert "verified" in info["label"].lower(), (
        f"label should mention 'verified' on pass, got {info['label']!r}"
    )


# ---------------------------------------------------------------------------
# 4. verification_result uncertain / failed → failed
# ---------------------------------------------------------------------------

def test_verification_result_uncertain_or_failed_shows_failed():
    """``outcome=uncertain`` and ``outcome=failed`` both mean the visual
    check didn't pass cleanly, so the chip transitions to ``failed``
    (red). The user should see the same surface for both so they know
    the render needs human attention."""
    rc, out, err = _run(r"""
const stubs = globalThis.__verifyChipFactory;
const textHistory = [];
const dataStateHistory = [];
const outcomes = ['uncertain', 'failed'];
const results = [];
for (const outcome of outcomes) {
  const textHistoryLocal = [];
  const dataStateHistoryLocal = [];
  const stubEl = {
    classList: { add: () => {}, remove: () => {}, toggle: () => {} },
    setAttribute: (k, v) => { if (k === 'data-state') dataStateHistoryLocal.push(v); },
    querySelector: (sel) => {
      if (sel === '.verify-chip-text') {
        return {
          get textContent() { return textHistoryLocal[textHistoryLocal.length - 1] || ''; },
          set textContent(v) { textHistoryLocal.push(v); },
        };
      }
      return { textContent: '' };
    },
  };
  const chip = stubs(stubEl);
  chip.onEvent({ type: 'verification_started', render_id: 'r1', frame_count: 1, stage: 'ready' });
  chip.onEvent({
    type: 'verification_result',
    render_id: 'r1',
    outcome,
    verdict_source: outcome === 'failed' ? 'model_explicit_fail' : 'model_explicit_uncertain',
    render_count: 1,
    max_renders: 3,
  });
  results.push({
    outcome,
    state: chip.getState().state,
    dataState: dataStateHistoryLocal[dataStateHistoryLocal.length - 1],
    label: textHistoryLocal[textHistoryLocal.length - 1] || '',
  });
}
console.log(JSON.stringify(results));
""")
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    rows = json.loads(out.strip().splitlines()[-1])
    for row in rows:
        assert row["state"] == "failed", (
            f"outcome={row['outcome']!r} should map to 'failed' state, got {row!r}"
        )
        assert row["dataState"] == "failed", (
            f"data-state should be 'failed' for outcome={row['outcome']!r}, got {row!r}"
        )
        assert "failed" in row["label"].lower(), (
            f"label should mention 'failed' for outcome={row['outcome']!r}, "
            f"got {row['label']!r}"
        )


# ---------------------------------------------------------------------------
# 5. verification_result skipped → skipped
# ---------------------------------------------------------------------------

def test_verification_result_skipped_shows_skipped():
    """``outcome=skipped`` is the path where the server itself decided
    not to run verification (e.g. text-only model, render failed). The
    chip should surface that with a ``skipped`` state and a neutral
    'Verification skipped' label — NOT a scary red 'failed'."""
    rc, out, err = _run(r"""
const stubs = globalThis.__verifyChipFactory;
const textHistory = [];
const dataStateHistory = [];
const stubEl = {
  classList: { add: () => {}, remove: () => {}, toggle: () => {} },
  setAttribute: (k, v) => { if (k === 'data-state') dataStateHistory.push(v); },
  querySelector: (sel) => {
    if (sel === '.verify-chip-text') {
      return {
        get textContent() { return textHistory[textHistory.length - 1] || ''; },
        set textContent(v) { textHistory.push(v); },
      };
    }
    return { textContent: '' };
  },
};
const chip = stubs(stubEl);
chip.onEvent({
  type: 'verification_result',
  render_id: 'r1',
  outcome: 'skipped',
  verdict_source: 'text_only_model',
  render_count: 1,
  max_renders: 3,
});
console.log(JSON.stringify({
  state: chip.getState().state,
  dataState: dataStateHistory[dataStateHistory.length - 1],
  label: textHistory[textHistory.length - 1] || '',
}));
""")
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    info = json.loads(out.strip().splitlines()[-1])
    assert info["state"] == "skipped", info
    assert info["dataState"] == "skipped", (
        f"data-state should be 'skipped', got {info!r}"
    )
    assert "skipped" in info["label"].lower(), (
        f"label should say 'skipped', got {info['label']!r}"
    )


# ---------------------------------------------------------------------------
# 6. verification_result capped → capped
# ---------------------------------------------------------------------------

def test_verification_result_capped_shows_capped():
    """``outcome=capped`` is the path where the per-turn render cap
    was hit. The chip should show ``capped`` (red) with a clear label
    so the user knows the loop was forced to stop."""
    rc, out, err = _run(r"""
const stubs = globalThis.__verifyChipFactory;
const textHistory = [];
const dataStateHistory = [];
const stubEl = {
  classList: { add: () => {}, remove: () => {}, toggle: () => {} },
  setAttribute: (k, v) => { if (k === 'data-state') dataStateHistory.push(v); },
  querySelector: (sel) => {
    if (sel === '.verify-chip-text') {
      return {
        get textContent() { return textHistory[textHistory.length - 1] || ''; },
        set textContent(v) { textHistory.push(v); },
      };
    }
    return { textContent: '' };
  },
};
const chip = stubs(stubEl);
chip.onEvent({
  type: 'verification_result',
  render_id: 'r1',
  outcome: 'capped',
  verdict_source: 'cap_reached',
  render_count: 4,
  max_renders: 3,
});
console.log(JSON.stringify({
  state: chip.getState().state,
  dataState: dataStateHistory[dataStateHistory.length - 1],
  label: textHistory[textHistory.length - 1] || '',
}));
""")
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    info = json.loads(out.strip().splitlines()[-1])
    assert info["state"] == "capped", info
    assert info["dataState"] == "capped", (
        f"data-state should be 'capped', got {info!r}"
    )
    assert "capped" in info["label"].lower(), (
        f"label should say 'capped', got {info['label']!r}"
    )


# ---------------------------------------------------------------------------
# 7. done resets the chip to idle
# ---------------------------------------------------------------------------

def test_done_resets_chip_to_idle():
    """After a turn finishes, the chip must reset to ``idle`` and
    re-hide. Per the v1.4 P1-2 brief pattern (chat-status clears
    within one frame of DONE/error), the verify chip follows the same
    convention: the per-turn progress indicator is removed so a fresh
    turn starts clean. The ``error`` event must reset to idle too
    (verified here as a bonus assertion)."""
    rc, out, err = _run(r"""
const stubs = globalThis.__verifyChipFactory;
const textHistory = [];
const dataStateHistory = [];
const classesAdded = new Set();
const classesRemoved = new Set();
const stubEl = {
  classList: {
    add: (c) => classesAdded.add(c),
    remove: (c) => classesRemoved.add(c),
    toggle: () => {},
  },
  setAttribute: (k, v) => { if (k === 'data-state') dataStateHistory.push(v); },
  querySelector: (sel) => {
    if (sel === '.verify-chip-text') {
      return {
        get textContent() { return textHistory[textHistory.length - 1] || ''; },
        set textContent(v) { textHistory.push(v); },
      };
    }
    return { textContent: '' };
  },
};
const chip = stubs(stubEl);
chip.onEvent({ type: 'verification_started', render_id: 'r1', frame_count: 1, stage: 'ready' });
chip.onEvent({
  type: 'verification_result',
  render_id: 'r1',
  outcome: 'pass',
  verdict_source: 'model_explicit_pass',
  render_count: 1,
  max_renders: 3,
});
chip.onEvent({ type: 'done', stop_reason: 'end_turn' });
const afterDone = {
  state: chip.getState().state,
  dataState: dataStateHistory[dataStateHistory.length - 1],
  hiddenAdded: classesAdded.has('hidden'),
  label: textHistory[textHistory.length - 1] || '',
};

// Drive a second pass: start, fail, then an error event (not done).
chip.onEvent({ type: 'verification_started', render_id: 'r2', frame_count: 1, stage: 'ready' });
chip.onEvent({
  type: 'verification_result',
  render_id: 'r2',
  outcome: 'failed',
  verdict_source: 'model_explicit_fail',
  render_count: 2,
  max_renders: 3,
});
chip.onEvent({ type: 'error', message: 'boom' });
const afterError = {
  state: chip.getState().state,
  dataState: dataStateHistory[dataStateHistory.length - 1],
  hiddenAdded: classesAdded.has('hidden'),
  label: textHistory[textHistory.length - 1] || '',
};

console.log(JSON.stringify({ afterDone, afterError }));
""")
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    info = json.loads(out.strip().splitlines()[-1])
    for key, snapshot in [("afterDone", info["afterDone"]), ("afterError", info["afterError"])]:
        assert snapshot["state"] == "idle", (
            f"{key}: chip should be idle after the terminal event, got {snapshot!r}"
        )
        assert snapshot["dataState"] == "idle", (
            f"{key}: data-state should be 'idle', got {snapshot!r}"
        )
        assert snapshot["hiddenAdded"] is True, (
            f"{key}: chip should re-add 'hidden' on reset so the next turn "
            f"starts hidden, got {snapshot!r}"
        )
        assert snapshot["label"] == "", (
            f"{key}: label should be empty in idle, got {snapshot['label']!r}"
        )
