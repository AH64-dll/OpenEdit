"""Tests for the frontend chat-status indicator (v1.4 P1-2).

The chat-status indicator is a small state machine that surfaces "AI
is running" / "AI is running tool X" / "AI stopped" feedback to the
user while a chat turn is in flight. The state is driven by the same
WS events the existing chat log already consumes (``text``,
``tool_start``, ``tool_result``, ``error``, ``done``); the indicator
must be in the right state at every transition.

The state machine is exposed as
``window.OpenEdit.__testHooks.createChatStatus(element)`` so Node-sandbox
tests can drive it without a real DOM (the existing pattern in
``test_serve_asset_stream.py``).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


_THIS_DIR = Path(__file__).resolve()
_REPO_ROOT = _THIS_DIR.parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

APP_JS = (
    _REPO_ROOT
    / "open_edit"
    / "open_edit"
    / "serve"
    / "static"
    / "app.js"
)
assert APP_JS.exists(), f"missing {APP_JS}"


# ---------------------------------------------------------------------------
# Harness factory
# ---------------------------------------------------------------------------

def _harness(script_body: str) -> tuple[str, str]:
    """Write a tiny Node script that loads app.js into a stubbed browser
    environment, then runs ``script_body``. Returns ``(script_text, path)``.
    """
    harness = r"""
'use strict';
const fs = require('fs');
const vm = require('vm');

const code = fs.readFileSync(process.argv[2], 'utf-8');

const stubElement = () => ({
  appendChild: () => {},
  setAttribute: () => {},
  addEventListener: () => {},
  classList: { add: () => {}, remove: () => {}, toggle: () => {} },
  dataset: {},
  style: {},
  children: [],
  textContent: '',
  innerHTML: '',
  value: '',
  removeAttribute: () => {},
  load: () => {},
  focus: () => {},
  click: () => {},
  replaceWith: () => {},
  remove: () => {},
});
const sandbox = {
  document: {
    createElement: () => stubElement(),
    createTextNode: (t) => ({ nodeType: 3, textContent: t }),
    addEventListener: () => {},
    querySelector: () => stubElement(),
    querySelectorAll: () => [],
  },
  window: { addEventListener: () => {} },
  localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
  WebSocket: function () { this.close = () => {}; },
  crypto: { randomUUID: () => 'test-uuid' },
  fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }),
  navigator: { clipboard: { writeText: () => Promise.resolve() } },
  Response: function () {},
  setTimeout: (fn) => fn && fn(),
  clearTimeout: () => {},
  Node: { TEXT_NODE: 3 },
  console: { warn: () => {}, error: () => {}, log: () => {} },
  location: { protocol: 'http:', host: 'localhost' },
};
sandbox.self = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(code, sandbox);
""" + script_body
    return harness


def _run_node_script(script: str) -> tuple[int, str, str]:
    """Write ``script`` to a temp file and run it with Node. The script
    receives the path to app.js as ``argv[2]``. Returns ``(returncode, stdout, stderr)``.
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(script)
        path = fh.name
    try:
        proc = subprocess.run(
            ["node", path, str(APP_JS)],
            capture_output=True, text=True, timeout=30,
        )
        return proc.returncode, proc.stdout, proc.stderr
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Test: state machine is exposed on __testHooks
# ---------------------------------------------------------------------------

def test_create_chat_status_is_exposed_on_test_hooks():
    """``window.OpenEdit.__testHooks.createChatStatus`` must exist so
    tests can drive the state machine. Without this hook the indicator
    would be untestable without spinning up a real browser."""
    script = _harness(r"""
const hooks = sandbox.window.OpenEdit && sandbox.window.OpenEdit.__testHooks;
if (!hooks) { console.error('NO_HOOKS'); process.exit(2); }
if (typeof hooks.createChatStatus !== 'function') {
  console.error('NO_CREATE_CHAT_STATUS');
  process.exit(3);
}
console.log('OK');
""")
    rc, out, err = _run_node_script(script)
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    assert out.strip().splitlines()[-1] == "OK", (
        f"expected OK, got {out!r} stderr={err!r}"
    )


# ---------------------------------------------------------------------------
# Test: full lifecycle of one turn (send → text → tool → result → text → done)
# ---------------------------------------------------------------------------

def test_chat_status_full_turn_lifecycle():
    """A complete turn walks the indicator through every state and ends
    back at idle. The sequence the backend actually emits (per
    ``serve/app.py``) is::

        text         (model starts streaming)
        tool_start   (model invokes a tool)
        tool_result  (tool returned)
        text         (model resumes streaming)
        done         (turn finished)

    The indicator must reflect each of these transitions."""
    script = _harness(r"""
const hooks = sandbox.window.OpenEdit.__testHooks;

// A stub element that records the state attribute and class changes.
let currentDataState = 'unset';
const classHistory = [];
const stubEl = {
  classList: {
    add: (c) => { if (!classHistory.includes(c)) classHistory.push(c); },
    remove: (c) => {
      const i = classHistory.indexOf(c);
      if (i >= 0) classHistory.splice(i, 1);
    },
    toggle: () => {},
  },
  dataset: {},
  setAttribute: (k, v) => { if (k === 'data-state') currentDataState = v; },
  querySelector: (sel) => {
    // The state machine looks up a child for the label text.
    return {
      textContent: '',
    };
  },
};

const status = hooks.createChatStatus(stubEl);

// Drive a typical turn.
const log = [];
const snap = (label) => log.push({
  label,
  state: status.getState(),
  dataState: currentDataState,
  hidden: classHistory.includes('hidden'),
});

// Initial state.
snap('initial');

// User clicks Send — indicator should show thinking immediately,
// before any WS event arrives.
status.send();
snap('after_send');

// First text delta.
status.onEvent({ type: 'text', text: 'Let me look.' });
snap('after_text');

// Tool starts.
status.onEvent({ type: 'tool_start', id: 't1', name: 'add_marker', input: {} });
snap('after_tool_start');

// Tool returns.
status.onEvent({ type: 'tool_result', id: 't1', name: 'add_marker', result: { ok: true } });
snap('after_tool_result');

// Model continues.
status.onEvent({ type: 'text', text: 'Done.' });
snap('after_text_2');

// Turn done.
status.onEvent({ type: 'done', stop_reason: 'end_turn' });
snap('after_done');

console.log(JSON.stringify(log));
""")
    rc, out, err = _run_node_script(script)
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    log = json.loads(out.strip().splitlines()[-1])

    by_label = {entry["label"]: entry for entry in log}

    # Initial: idle, indicator hidden.
    assert by_label["initial"]["state"]["state"] == "idle", by_label["initial"]
    assert by_label["initial"]["dataState"] == "idle"
    assert by_label["initial"]["hidden"] is True

    # After send: thinking, indicator visible, dataset.state="thinking".
    s = by_label["after_send"]["state"]
    assert s["state"] == "thinking", s
    assert s["toolName"] is None
    assert by_label["after_send"]["dataState"] == "thinking"
    assert by_label["after_send"]["hidden"] is False

    # After text delta: still thinking (text confirms the model is responding).
    assert by_label["after_text"]["state"]["state"] == "thinking"

    # After tool_start: tool_running, with the tool name carried in the
    # payload so the UI can show "Running add_marker…".
    s = by_label["after_tool_start"]["state"]
    assert s["state"] == "tool_running", s
    assert s["toolName"] == "add_marker", s
    assert by_label["after_tool_start"]["dataState"] == "tool_running"

    # After tool_result: back to thinking — the model will either emit
    # more text or a done event next.
    assert by_label["after_tool_result"]["state"]["state"] == "thinking"

    # After more text: still thinking.
    assert by_label["after_text_2"]["state"]["state"] == "thinking"

    # After done: idle, indicator hidden.
    s = by_label["after_done"]["state"]
    assert s["state"] == "idle", s
    assert by_label["after_done"]["hidden"] is True


# ---------------------------------------------------------------------------
# Test: tool name surfaces in the rendered label
# ---------------------------------------------------------------------------

def test_chat_status_label_contains_tool_name_in_tool_running_state():
    """The user-visible label for ``tool_running`` must include the tool
    name (e.g. "Running add_marker…") so the user knows what the AI is
    doing. The state machine updates a child text node — the test
    inspects the textContent of that node after each transition."""
    script = _harness(r"""
const hooks = sandbox.window.OpenEdit.__testHooks;

const textNodes = new Map();
const stubEl = {
  classList: { add: () => {}, remove: () => {}, toggle: () => {} },
  dataset: {},
  setAttribute: () => {},
  querySelector: (sel) => {
    if (!textNodes.has(sel)) textNodes.set(sel, { textContent: '' });
    return textNodes.get(sel);
  },
};

const status = hooks.createChatStatus(stubEl);

status.send();
const thinkLabel = textNodes.get('.chat-status-text').textContent;

status.onEvent({ type: 'tool_start', id: 't1', name: 'search_pexels', input: { q: 'cats' } });
const toolLabel = textNodes.get('.chat-status-text').textContent;

status.onEvent({ type: 'tool_result', id: 't1', name: 'search_pexels', result: [] });
const afterLabel = textNodes.get('.chat-status-text').textContent;

console.log(JSON.stringify({ thinkLabel, toolLabel, afterLabel }));
""")
    rc, out, err = _run_node_script(script)
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    labels = json.loads(out.strip().splitlines()[-1])

    # "Thinking" label exists and is non-empty.
    assert labels["thinkLabel"], f"thinking label should be non-empty, got {labels!r}"
    # Tool label must include the tool name.
    assert "search_pexels" in labels["toolLabel"], (
        f"tool label should include the tool name 'search_pexels', got "
        f"{labels['toolLabel']!r} — the user can't tell which tool is running"
    )
    # After the tool result, the label is back to the thinking label
    # (the model will either emit more text or a done next).
    assert labels["afterLabel"] == labels["thinkLabel"], (
        f"after tool_result, label should match thinking label "
        f"({labels['thinkLabel']!r}), got {labels['afterLabel']!r}"
    )


# ---------------------------------------------------------------------------
# Test: error state surfaces to the user, then DONE clears it
# ---------------------------------------------------------------------------

def test_chat_status_error_then_done_clears():
    """A turn-level ``error`` event switches the indicator to the
    ``error`` state so the user can see the request failed. The
    subsequent ``done`` (which the backend always sends after an error,
    per ``app.py``) clears the indicator back to idle."""
    script = _harness(r"""
const hooks = sandbox.window.OpenEdit.__testHooks;
let currentDataState = 'unset';
const classHistory = [];
const stubEl = {
  classList: {
    add: (c) => { if (!classHistory.includes(c)) classHistory.push(c); },
    remove: (c) => { const i = classHistory.indexOf(c); if (i >= 0) classHistory.splice(i, 1); },
    toggle: () => {},
  },
  dataset: {},
  setAttribute: (k, v) => { if (k === 'data-state') currentDataState = v; },
  querySelector: () => ({ textContent: '' }),
};
const status = hooks.createChatStatus(stubEl);

const log = [];
status.send();
log.push({ at: 'send', state: status.getState().state, dataState: currentDataState, hidden: classHistory.includes('hidden') });
status.onEvent({ type: 'error', message: 'boom' });
log.push({ at: 'error', state: status.getState().state, dataState: currentDataState, hidden: classHistory.includes('hidden') });
status.onEvent({ type: 'done', stop_reason: 'error' });
log.push({ at: 'done', state: status.getState().state, dataState: currentDataState, hidden: classHistory.includes('hidden') });
console.log(JSON.stringify(log));
""")
    rc, out, err = _run_node_script(script)
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    log = json.loads(out.strip().splitlines()[-1])
    by_at = {entry["at"]: entry for entry in log}

    # After send: thinking.
    assert by_at["send"]["state"] == "thinking"
    assert by_at["send"]["hidden"] is False

    # After error: error state, indicator still visible.
    s = by_at["error"]
    assert s["state"] == "error", s
    assert s["dataState"] == "error"
    assert s["hidden"] is False, "error state should keep indicator visible"

    # After done: back to idle and hidden.
    s = by_at["done"]
    assert s["state"] == "idle", s
    assert s["dataState"] == "idle"
    assert s["hidden"] is True, "done should hide the indicator"


# ---------------------------------------------------------------------------
# Test: rapid back-to-back sends don't break the state machine
# ---------------------------------------------------------------------------

def test_chat_status_rapid_back_to_back_sends_dont_get_stuck():
    """A second ``send()`` while the indicator is still showing the
    previous turn must reset to ``thinking`` cleanly. The indicator
    must NOT get stuck in ``tool_running`` or ``error`` from a prior
    turn, and must NOT get stuck visible after a previous ``done``."""
    script = _harness(r"""
const hooks = sandbox.window.OpenEdit.__testHooks;
let currentDataState = 'unset';
const classHistory = [];
const stubEl = {
  classList: {
    add: (c) => { if (!classHistory.includes(c)) classHistory.push(c); },
    remove: (c) => { const i = classHistory.indexOf(c); if (i >= 0) classHistory.splice(i, 1); },
    toggle: () => {},
  },
  dataset: {},
  setAttribute: (k, v) => { if (k === 'data-state') currentDataState = v; },
  querySelector: () => ({ textContent: '' }),
};
const status = hooks.createChatStatus(stubEl);

const log = [];
const snap = (label) => log.push({ label, state: status.getState().state, dataState: currentDataState, hidden: classHistory.includes('hidden') });

// First turn.
status.send();
snap('turn1.send');
status.onEvent({ type: 'text', text: 'first turn' });
snap('turn1.text');
status.onEvent({ type: 'tool_start', id: 't1', name: 'add_marker' });
snap('turn1.tool_start');
// User hits send again WITHOUT a tool_result or done from turn 1.
status.send();
snap('turn1.interrupted_by_send');
// New turn's events.
status.onEvent({ type: 'text', text: 'second turn' });
snap('turn2.text');
status.onEvent({ type: 'done' });
snap('turn2.done');
// User sends a third message AFTER everything is idle.
status.send();
snap('turn3.send');
status.onEvent({ type: 'done' });
snap('turn3.done');

console.log(JSON.stringify(log));
""")
    rc, out, err = _run_node_script(script)
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    log = json.loads(out.strip().splitlines()[-1])
    by = {entry["label"]: entry for entry in log}

    # turn 1 walks normally.
    assert by["turn1.send"]["state"] == "thinking"
    assert by["turn1.text"]["state"] == "thinking"
    assert by["turn1.tool_start"]["state"] == "tool_running"

    # A new send() in the middle of turn 1 must reset the state.
    s = by["turn1.interrupted_by_send"]
    assert s["state"] == "thinking", (
        f"a second send() while a tool is running must reset to "
        f"'thinking', got {s!r} — the indicator would be stuck showing "
        f"the old tool name"
    )
    assert s["hidden"] is False

    # New turn runs through and ends cleanly.
    assert by["turn2.text"]["state"] == "thinking"
    s = by["turn2.done"]
    assert s["state"] == "idle", s
    assert s["hidden"] is True

    # Third turn: send after a fully-idle state must show the indicator.
    assert by["turn3.send"]["state"] == "thinking"
    assert by["turn3.send"]["hidden"] is False
    # And a done must clear it.
    s = by["turn3.done"]
    assert s["state"] == "idle", s
    assert s["hidden"] is True
