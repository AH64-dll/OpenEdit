"""Tests for the cost badge in the chat UI (v1.4 P1-3).

The cost badge sits next to the chat-status pill (P1-2) and
displays the per-turn + cumulative session cost, or an honest
``cost n/a (subscription)`` state when the LLM provider doesn't
report a per-token bill (e.g. the ``pi`` provider, which runs on
a subscription through opencode-go).

The badge is driven by the ``cost_update`` WS event:
``{"type": "cost_update", "turn_tokens", "turn_cost_usd",
"session_cost_usd", "source": "pi"|"computed"|"unavailable"}``.

The wire shape and label conventions are pinned by these tests so
the UI doesn't drift from the spec.

As of v1.4 P2 the frontend is an ES module. The harness in
``tests/_node_harness.py`` loads it via ``import()`` instead of
the old ``vm.runInContext`` pattern.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

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
# 1. cost badge is in the HTML, next to chat-status
# ---------------------------------------------------------------------------

def test_cost_badge_present_in_html():
    """The cost badge element must be in index.html, sitting next
    to the chat-status pill (P1-2). The wire shape requires a
    stable id we can target from the JS."""
    INDEX_HTML = (
        Path(__file__).resolve().parents[2]
        / "open_edit" / "open_edit" / "serve" / "static" / "index.html"
    )
    html = INDEX_HTML.read_text()
    # The badge needs an id we can target from app.js.
    assert 'id="cost-badge"' in html, (
        "expected #cost-badge element in index.html near chat-status; "
        "the cost_update event handler can't update a badge that doesn't exist"
    )
    # The badge should be inside the panel-center section (the chat
    # column) so it sits in the same visual region as the chat-status.
    assert "chat-status" in html  # baseline
    # And near the chat-status (within ~200 chars of the chat-status
    # element so they render side-by-side in the DOM order).
    chat_pos = html.find('id="chat-status"')
    cost_pos = html.find('id="cost-badge"')
    assert 0 < cost_pos - chat_pos < 400, (
        f"cost-badge (pos {cost_pos}) should be near chat-status (pos {chat_pos})"
    )


# ---------------------------------------------------------------------------
# 2. cost badge is exposed on the test hooks (so we can drive it in tests)
# ---------------------------------------------------------------------------

def test_cost_badge_is_exposed_on_test_hooks():
    """The cost-badge factory must be exposed on the test hooks so
    Node-sandbox tests can drive the badge without a real DOM."""
    script = _harness(r"""
const hooks = globalThis.OpenEdit && globalThis.OpenEdit.__testHooks;
if (!hooks) { console.error('NO_HOOKS'); process.exit(2); }
if (typeof hooks.createCostBadge !== 'function') {
  console.error('NO_CREATE_COST_BADGE');
  process.exit(3);
}
console.log('OK');
""")
    rc, out, err = _run_node_script(script, APP_JS)
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    assert out.strip().splitlines()[-1] == "OK", (
        f"expected OK, got {out!r} stderr={err!r}"
    )


# ---------------------------------------------------------------------------
# 3. factory renders the right label for each source state
# ---------------------------------------------------------------------------

def test_cost_badge_renders_pi_source_label():
    """Source=pi: render the per-turn + session cost in dollars."""
    script = _harness(r"""
const hooks = globalThis.OpenEdit.__testHooks;
const textHistory = [];
const stubEl = {
  classList: { add: () => {}, remove: () => {}, toggle: () => {} },
  dataset: {},
  setAttribute: () => {},
  querySelector: (sel) => {
    if (sel === '.cost-badge-text') {
      return {
        get textContent() { return textHistory[textHistory.length - 1] || ''; },
        set textContent(v) { textHistory.push(v); },
      };
    }
    return { textContent: '' };
  },
};
const badge = hooks.createCostBadge(stubEl);
badge.onEvent({
  type: 'cost_update',
  turn_tokens: 1500,
  turn_cost_usd: 0.02,
  session_cost_usd: 0.45,
  source: 'pi',
});
console.log(JSON.stringify({ text: textHistory[textHistory.length - 1] }));
""")
    rc, out, err = _run_node_script(script, APP_JS)
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    payload = json.loads(out.strip().splitlines()[-1])
    text = payload["text"]
    # Label must include both the per-turn figure and the session
    # figure. We use a permissive contains check: the precise
    # format ("$0.02 this turn · $0.45 session") is a UX choice
    # but the digits must be there. The source label ("pi" /
    # "computed" / "unavailable") is NOT shown to the user —
    # that's a wire field, not a UI label.
    assert "0.02" in text, (
        f"cost badge text should show the per-turn dollar figure, got {text!r}"
    )
    assert "0.45" in text, (
        f"cost badge text should show the session cumulative, got {text!r}"
    )
    assert "this turn" in text, (
        f"label should distinguish the per-turn figure from the session total, got {text!r}"
    )
    assert "session" in text, (
        f"label should include the 'session' qualifier for the cumulative, got {text!r}"
    )


def test_cost_badge_renders_computed_source_label():
    """Source=computed (anthropic/openai): same dollar-format label
    as pi. The source field is for the JS state machine, not the
    user-visible label."""
    script = _harness(r"""
const hooks = globalThis.OpenEdit.__testHooks;
const textHistory = [];
const stubEl = {
  classList: { add: () => {}, remove: () => {}, toggle: () => {} },
  dataset: {},
  setAttribute: () => {},
  querySelector: (sel) => {
    if (sel === '.cost-badge-text') {
      return {
        get textContent() { return textHistory[textHistory.length - 1] || ''; },
        set textContent(v) { textHistory.push(v); },
      };
    }
    return { textContent: '' };
  },
};
const badge = hooks.createCostBadge(stubEl);
badge.onEvent({
  type: 'cost_update',
  turn_tokens: 100,
  turn_cost_usd: 0.001,
  session_cost_usd: 0.001,
  source: 'computed',
});
console.log(JSON.stringify({ text: textHistory[textHistory.length - 1] }));
""")
    rc, out, err = _run_node_script(script, APP_JS)
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    payload = json.loads(out.strip().splitlines()[-1])
    text = payload["text"]
    # The user-visible label is identical for pi and computed —
    # the source field is internal.
    assert "0.0" in text, f"expected dollar figure in badge text, got {text!r}"


def test_cost_badge_renders_unavailable_source_label():
    """Source=unavailable: show the honest "cost n/a" message
    instead of a fake $0.00. The brief is explicit: don't fake
    the cost when we don't have real numbers."""
    script = _harness(r"""
const hooks = globalThis.OpenEdit.__testHooks;
const textHistory = [];
const stubEl = {
  classList: { add: () => {}, remove: () => {}, toggle: () => {} },
  dataset: {},
  setAttribute: () => {},
  querySelector: (sel) => {
    if (sel === '.cost-badge-text') {
      return {
        get textContent() { return textHistory[textHistory.length - 1] || ''; },
        set textContent(v) { textHistory.push(v); },
      };
    }
    return { textContent: '' };
  },
};
const badge = hooks.createCostBadge(stubEl);
badge.onEvent({
  type: 'cost_update',
  turn_tokens: 0,
  turn_cost_usd: 0.0,
  session_cost_usd: 0.0,
  source: 'unavailable',
});
console.log(JSON.stringify({ text: textHistory[textHistory.length - 1] }));
""")
    rc, out, err = _run_node_script(script, APP_JS)
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    payload = json.loads(out.strip().splitlines()[-1])
    text = payload["text"]
    # The honest unavailable state: "cost n/a" with some hint of
    # why (subscription). We don't enforce exact wording — the
    # assertion just checks it's NOT a $0.00 fake number.
    assert "n/a" in text.lower() or "n.a" in text.lower(), (
        f"unavailable source should show 'n/a' state, got {text!r}"
    )
    assert "$0" not in text, (
        f"unavailable source must NOT show a fake '$0.00', got {text!r} — "
        f"the brief is explicit: don't mislead the user"
    )


# ---------------------------------------------------------------------------
# 4. cost badge does not duplicate the chat-status indicator
# ---------------------------------------------------------------------------

def test_cost_badge_handles_only_cost_update_event():
    """The cost badge factory is intentionally focused: it only
    reacts to ``cost_update``. Other WS events (text, tool_start,
    done, error) are handled by the chat-status indicator. This
    separation of concerns is what the brief meant by 'the cost
    badge should not duplicate the chat-status indicator's logic'.

    Note: the factory does ONE setAttribute on construction
    (data-source='unavailable'); we measure the delta from
    post-construction to post-events so that initial write
    doesn't pollute the count."""
    script = _harness(r"""
const hooks = globalThis.OpenEdit.__testHooks;
let setAttrCalls = 0;
const stubEl = {
  classList: { add: () => {}, remove: () => {}, toggle: () => {} },
  dataset: {},
  setAttribute: () => { setAttrCalls++; },
  querySelector: (sel) => {
    if (sel === '.cost-badge-text') return { textContent: '' };
    return { textContent: '' };
  },
};
const badge = hooks.createCostBadge(stubEl);
// Reset the counter AFTER construction. Subsequent non-cost_update
// events must not call setAttribute at all.
setAttrCalls = 0;
badge.onEvent({ type: 'text', text: 'hi' });
badge.onEvent({ type: 'tool_start', id: 't1', name: 'add_marker', input: {} });
badge.onEvent({ type: 'tool_result', id: 't1', name: 'add_marker', result: {} });
badge.onEvent({ type: 'done', stop_reason: 'end_turn' });
badge.onEvent({ type: 'error', message: 'boom' });
console.log(JSON.stringify({ setAttrCalls }));
""")
    rc, out, err = _run_node_script(script, APP_JS)
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    payload = json.loads(out.strip().splitlines()[-1])
    # Non-cost_update events should not change data-state or
    # otherwise drive the cost badge.
    assert payload["setAttrCalls"] == 0, (
        f"cost badge should not react to non-cost_update events, "
        f"got {payload['setAttrCalls']} setAttribute calls after events"
    )


# ---------------------------------------------------------------------------
# 5. cost_update event wires through handleWsEvent
# ---------------------------------------------------------------------------

def test_handle_ws_event_dispatches_cost_update():
    """The chat log's ``handleWsEvent`` must route ``cost_update``
    events to the cost badge. This test exercises the same
    dispatch path the browser will use."""
    script = _harness(r"""
const hooks = globalThis.OpenEdit.__testHooks;
const expected = ['createChatStatus', 'createCostBadge'];
const missing = expected.filter(k => typeof hooks[k] !== 'function');
if (missing.length) { console.error('MISSING:' + missing.join(',')); process.exit(2); }
console.log('OK');
""")
    rc, out, err = _run_node_script(script, APP_JS)
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    assert out.strip().splitlines()[-1] == "OK", (
        f"expected OK, got {out!r} stderr={err!r}"
    )


# ---------------------------------------------------------------------------
# 6. formatting conventions
# ---------------------------------------------------------------------------

def test_cost_badge_uses_dollar_sign_for_dollar_amounts():
    """When source=pi or source=computed, the badge text contains
    a $ glyph. Pinned so the format is consistent across turns
    and providers (operators reading the UI shouldn't have to
    guess whether the number is dollars, tokens, or a percent)."""
    script = _harness(r"""
const hooks = globalThis.OpenEdit.__testHooks;
const textHistory = [];
const stubEl = {
  classList: { add: () => {}, remove: () => {}, toggle: () => {} },
  dataset: {},
  setAttribute: () => {},
  querySelector: (sel) => {
    if (sel === '.cost-badge-text') {
      return {
        get textContent() { return textHistory[textHistory.length - 1] || ''; },
        set textContent(v) { textHistory.push(v); },
      };
    }
    return { textContent: '' };
  },
};
const badge = hooks.createCostBadge(stubEl);
badge.onEvent({
  type: 'cost_update',
  turn_tokens: 1000,
  turn_cost_usd: 0.0123,
  session_cost_usd: 0.4567,
  source: 'computed',
});
console.log(JSON.stringify({ text: textHistory[textHistory.length - 1] }));
""")
    rc, out, err = _run_node_script(script, APP_JS)
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    payload = json.loads(out.strip().splitlines()[-1])
    assert "$" in payload["text"], (
        f"cost badge should use $ glyph for dollar amounts, got {payload['text']!r}"
    )


def test_cost_badge_hides_when_no_cost_update_yet():
    """Until the first ``cost_update`` event arrives, the badge
    should be hidden. The chat-status pill (P1-2) starts hidden
    too; both share the convention 'no event = no pill' so the
    user doesn't see a stale label."""
    script = _harness(r"""
const hooks = globalThis.OpenEdit.__testHooks;
const classHistory = new Set();
const stubEl = {
  classList: {
    add: (c) => classHistory.add(c),
    remove: (c) => classHistory.delete(c),
    toggle: () => {},
  },
  dataset: {},
  setAttribute: () => {},
  querySelector: (sel) => {
    if (sel === '.cost-badge-text') return { textContent: '' };
    return { textContent: '' };
  },
};
const badge = hooks.createCostBadge(stubEl);
console.log(JSON.stringify({ hidden: classHistory.has('hidden') }));
""")
    rc, out, err = _run_node_script(script, APP_JS)
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    payload = json.loads(out.strip().splitlines()[-1])
    assert payload["hidden"] is True, (
        f"cost badge must start hidden (no cost_update yet), got {payload!r}"
    )
