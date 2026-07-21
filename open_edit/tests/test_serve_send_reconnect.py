"""Tests for the v1.4 P2 review fix to the Send click path.

The original report ("Discipline: the sendChatMessage → scheduleReconnect
call in the old IIFE was dropped") flagged a real regression: the new
modular structure removed the manual ``scheduleReconnect`` call that
used to fire from the click path when ``sendChatMessage`` returned
false. The reviewer's fix recommendation: pin the CONNECTING-stuck edge
case so a future refactor doesn't reintroduce the regression.

The edge case the test pins:

  1. The WebSocket is in ``CONNECTING`` state (readyState === 0).
  2. The user clicks Send.
  3. ``sendChatMessage`` sees readyState !== OPEN, shows the
     "Not connected. Retrying…" toast, returns false.
  4. **The system kicks a ``scheduleReconnect()`` so the next
     attempt has a chance to land.** Without this, a stalled
     handshake (browser tab throttling, hung TCP) leaves the user
     stuck on the toast with no actual retry.

The auto-reconnect in ``ws.js``'s ``onclose`` handler covers the
normal disconnect case, but ``onclose`` does not fire while a
socket is still in CONNECTING — that's the gap this test pins.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow ``from _node_harness import ...`` from the tests/ dir.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _node_harness import (  # noqa: E402
    app_js_path,
    harness as _harness,
    run_node_script as _run_node_script,
)

APP_JS = app_js_path()
assert APP_JS.exists(), f"missing {APP_JS}"


# ---------------------------------------------------------------------------
# Test: handleSend kicks scheduleReconnect when the WS is in CONNECTING
# ---------------------------------------------------------------------------

def test_handle_send_kicks_reconnect_when_ws_is_connecting():
    """Regression: clicking Send while the WS is in CONNECTING state
    must kick a ``scheduleReconnect`` so the user is not stuck on the
    "Not connected. Retrying…" toast with no actual retry.

    The CONNECTING state is the one the auto-reconnect in ws.js's
    onclose handler does not cover (onclose only fires once the
    socket is closing or has closed). This test pins the click-path
    contract: when sendChatMessage bails because the WS isn't open,
    the caller (handleSend in app.js) is responsible for forcing
    a reconnect.
    """
    script = _harness(r"""
const OpenEdit = globalThis.OpenEdit;
if (!OpenEdit) { console.error('NO_OPENEDIT'); process.exit(2); }
if (typeof OpenEdit.__testHooks.handleSend !== 'function') {
  console.error('NO_HANDLE_SEND_HOOK');
  process.exit(2);
}

// Stub the chat input that handleSend reads from.
const chatInput = {
  value: 'hello world',
  trim: function () { return this.value; },
  addEventListener: () => {},
  focus: () => {},
  style: {},
  disabled: false,
};
// The toast stub: handleSend does not call showToast directly,
// but sendChatMessage does (it bails before reaching the user
// message path). We don't assert on the toast; we just need it
// to not crash.
const toast = { textContent: '', className: '', classList: { add: () => {}, remove: () => {} } };
globalThis.document.querySelector = (sel) => {
  if (sel === '#chat-input') return chatInput;
  if (sel === '#toast') return toast;
  return {
    addEventListener: () => {},
    classList: { add: () => {}, remove: () => {}, toggle: () => {} },
    setAttribute: () => {},
    dataset: {},
    style: {},
    textContent: '',
    innerHTML: '',
    value: '',
    appendChild: () => {},
    removeChild: () => {},
    querySelector: () => null,
    querySelectorAll: () => [],
  };
};
globalThis.document.querySelectorAll = () => [];

// --- Set up a STALLED CONNECTING state --------------------------------
// readyState === 0 is WebSocket.CONNECTING. sendChatMessage checks
// ``state.ws.readyState !== 1`` (OPEN) and bails — the precise edge
// case the reviewer flagged.
OpenEdit.state.currentProjectId = 'p1';
OpenEdit.state.ws = { readyState: 0, send: () => {} };
OpenEdit.state.conversationId = 'c1';
OpenEdit.state.reconnectAttempts = 0;
OpenEdit.state.reconnectTimer = null;
OpenEdit.state.chatStatus = null;

// --- Drive the click path --------------------------------------------
OpenEdit.__testHooks.handleSend();

// --- Assert scheduleReconnect was called -----------------------------
// scheduleReconnect sets state.reconnectTimer to the new timeout
// handle and bumps state.reconnectAttempts.
const reconnectScheduled = OpenEdit.state.reconnectTimer !== null;
const reconnectAttempts = OpenEdit.state.reconnectAttempts;

console.log(JSON.stringify({
  reconnectScheduled,
  reconnectAttempts,
}));
""")
    rc, out, err = _run_node_script(script, APP_JS)
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    res = json.loads(out.strip().splitlines()[-1])

    # The headline assertion: handleSend kicked scheduleReconnect.
    assert res["reconnectScheduled"], (
        f"expected handleSend to kick scheduleReconnect when the WS is "
        f"in CONNECTING state, but state.reconnectTimer is still null. "
        f"Got: {res!r}. The user would be stuck on the 'Not connected. "
        f"Retrying…' toast with no actual retry."
    )
    assert res["reconnectAttempts"] >= 1, (
        f"expected handleSend to bump reconnectAttempts via "
        f"scheduleReconnect, got: {res!r}"
    )
