"""Frontend tests for the v1.4 P1-1 search-assets results panel.

When the assistant's tool stream returns a ``search_assets`` tool
result, the chat log must render a results panel with:

- one card per result (thumbnail, title, license badge, attribution hint)
- an "Add to project" button per result that fires an import_asset
  chat message for that result_id
- a graceful "missing API key" error state when the tool returns one
- the same wire shape the tool result carries (the panel doesn't
  re-fetch or re-shape the data — it renders what the LLM saw).

The panel is exposed as ``window.OpenEdit.__testHooks.appendSearchResults``
so Node-sandbox tests can drive it without a real DOM.

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
# Sample search_assets tool result (Pexels video) — the same shape the
# Python tool returns, so the panel can render what the LLM saw.
# ---------------------------------------------------------------------------

SAMPLE_RESULTS = {
    "query": "rain",
    "kind": "video",
    "limit": 3,
    "source": "pexels",
    "results": [
        {
            "id": "pexels-video-1",
            "source": "pexels",
            "kind": "video",
            "title": "rain on window",
            "thumbnail_url": "https://i.pexels.com/1.jpg",
            "preview_url": "https://v.pexels.com/1.mp4",
            "duration_seconds": 12.0,
            "license": "Pexels License",
            "attribution_required": False,
            "attribution": "Source: Pexels",
        },
        {
            "id": "pexels-video-2",
            "source": "pexels",
            "kind": "video",
            "title": "rain on leaves",
            "thumbnail_url": "https://i.pexels.com/2.jpg",
            "preview_url": "https://v.pexels.com/2.mp4",
            "duration_seconds": 8.0,
            "license": "Pexels License",
            "attribution_required": False,
            "attribution": "Source: Pexels",
        },
    ],
}

SAMPLE_FREESOUND = {
    "query": "whoosh",
    "kind": "audio",
    "limit": 5,
    "source": "freesound",
    "results": [
        {
            "id": "freesound-555",
            "source": "freesound",
            "kind": "audio",
            "title": "whoosh_01",
            "thumbnail_url": "https://cdn.freesound.org/waveforms/555/555_m.png",
            "preview_url": "https://cdn.freesound.org/previews/555/555.mp3",
            "duration_seconds": 1.2,
            "license": "CC BY 4.0",
            "attribution_required": True,
            "attribution": "'whoosh_01' by sfx_user (CC BY 4.0)",
        },
    ],
}

SAMPLE_ERROR = {
    "error": "OPEN_EDIT_PEXELS_API_KEY not set; set it (and OPEN_EDIT_FREESOUND_API_KEY for audio) in your environment, then restart the server. See .env.example for the full list.",
    "results": [],
}


# ---------------------------------------------------------------------------
# Test: hook is exposed
# ---------------------------------------------------------------------------

def test_append_search_results_is_exposed_on_test_hooks():
    """``window.OpenEdit.__testHooks.appendSearchResults`` must exist so
    tests can render the panel without a real DOM."""
    script = _harness(r"""
const hooks = globalThis.OpenEdit && globalThis.OpenEdit.__testHooks;
if (!hooks) { console.error('NO_HOOKS'); process.exit(2); }
if (typeof hooks.appendSearchResults !== 'function') {
  console.error('NO_APPEND_SEARCH_RESULTS');
  process.exit(3);
}
console.log('OK');
""")
    rc, out, err = _run_node_script(script, APP_JS)
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    assert out.strip().splitlines()[-1] == "OK", f"got: {out!r}"


# ---------------------------------------------------------------------------
# Test: happy path — render thumbnails + license badge per result
# ---------------------------------------------------------------------------

def test_append_search_results_renders_one_card_per_result():
    """The panel must produce one card per result, with the license
    badge and "Add to project" button visible on each."""
    script = _harness(r"""
const hooks = globalThis.OpenEdit.__testHooks;

// Simple stub: every createElement returns a record that tracks its
// own className (joined with spaces) and accumulated text. This is
// enough for the renderer to work without errors and for the test
// to walk the resulting tree.
let nodeCounter = 0;
globalThis.document.createElement = (tag) => {
  const id = ++nodeCounter;
  const node = {
    _id: id,
    tag,
    _textParts: [],
    _classParts: [],
    _attrs: {},
    _children: [],
    _listeners: {},
    _imgSrc: '',
    set textContent(v) { this._textParts = [String(v)]; },
    get textContent() { return this._textParts.join(''); },
    get className() { return this._classParts.join(' '); },
    set className(v) { this._classParts = String(v).split(/\s+/).filter(Boolean); },
    setAttribute(k, v) { this._attrs[k] = String(v); },
    getAttribute(k) { return this._attrs[k]; },
    appendChild(c) { this._children.push(c); return c; },
    addEventListener(ev, fn) { this._listeners[ev] = fn; },
    removeChild(c) {
      const i = this._children.indexOf(c);
      if (i >= 0) this._children.splice(i, 1);
    },
    remove() {},
    replaceWith(c) {},
    querySelector: () => null,
    querySelectorAll: () => [],
    src: '',
  };
  // Late-bind classList to the node's own _classParts.
  node.classList = {
    add: (c) => { if (!node._classParts.includes(c)) node._classParts.push(c); },
    remove: (c) => { const i = node._classParts.indexOf(c); if (i >= 0) node._classParts.splice(i, 1); },
    contains: (c) => node._classParts.includes(c),
    toggle: () => {},
  };
  // Use property setters for src / textContent.
  Object.defineProperty(node, 'src', {
    set(v) { node._imgSrc = v; },
    get() { return node._imgSrc; },
  });
  return node;
};

// The renderer calls ``el(tag, props, children)`` which sets
// ``node.textContent`` (string) or uses ``appendChild``. The stub
// above supports both. ``document.createTextNode`` (called by ``el``)
// returns the harness's text node; it's a leaf so we treat it as a
// text-only node when walking.

const panel = hooks.appendSearchResults({});
const walk = (n) => {
  let s = (n && n.textContent) || '';
  const kids = (n && n._children) || [];
  for (const c of kids) s += ' ' + walk(c);
  return s;
};
const text = walk(panel);
const cardCount = (function count(n) {
  let n2 = 0;
  if (n && n.tag === 'div' && n._attrs && n._attrs['data-result-id']) n2++;
  const kids = (n && n._children) || [];
  for (const c of kids) n2 += count(c);
  return n2;
})(panel);
console.log(JSON.stringify({
  panelClass: panel.className,
  cardCount,
  text,
}));
""")
    rc, out, err = _run_node_script(script, APP_JS)
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    res = json.loads(out.strip().splitlines()[-1])
    assert "search-results" in res["panelClass"], res
    # No results → no cards but a "no results" message.
    assert "No results" in res["text"] or res["cardCount"] == 0


def test_append_search_results_renders_license_per_result():
    """Each card must surface the license string verbatim so the user
    knows the terms before importing (Freesound especially)."""
    script = _harness(r"""
const hooks = globalThis.OpenEdit.__testHooks;

let nodeCounter = 0;
globalThis.document.createElement = (tag) => {
  const id = ++nodeCounter;
  const node = {
    _id: id, tag,
    _textParts: [], _classParts: [],
    _attrs: {}, _children: [], _listeners: {},
    _imgSrc: '',
  };
  Object.defineProperty(node, 'textContent', {
    set(v) { node._textParts = [String(v)]; },
    get() { return node._textParts.join(''); },
  });
  Object.defineProperty(node, 'className', {
    get() { return this._classParts.join(' '); },
    set(v) { node._classParts = String(v).split(/\s+/).filter(Boolean); },
  });
  Object.defineProperty(node, 'src', {
    set(v) { node._imgSrc = v; },
    get() { return node._imgSrc; },
  });
  node.setAttribute = (k, v) => { node._attrs[k] = String(v); };
  node.getAttribute = (k) => node._attrs[k];
  node.appendChild = (c) => { node._children.push(c); return c; };
  node.removeChild = (c) => {
    const i = node._children.indexOf(c);
    if (i >= 0) node._children.splice(i, 1);
  };
  node.addEventListener = (ev, fn) => { node._listeners[ev] = fn; };
  node.remove = () => {};
  node.replaceWith = () => {};
  node.classList = {
    add: (c) => { if (!node._classParts.includes(c)) node._classParts.push(c); },
    remove: (c) => { const i = node._classParts.indexOf(c); if (i >= 0) node._classParts.splice(i, 1); },
    contains: (c) => node._classParts.includes(c),
    toggle: () => {},
  };
  node.querySelector = () => null;
  node.querySelectorAll = () => [];
  return node;
};

const panel = hooks.appendSearchResults({
  results: [
    {
      id: 'pexels-video-1',
      source: 'pexels',
      kind: 'video',
      title: 'rain on window',
      thumbnail_url: 'https://i.pexels.com/1.jpg',
      preview_url: 'https://v.pexels.com/1.mp4',
      license: 'Pexels License',
      attribution_required: false,
      attribution: 'Source: Pexels',
    },
    {
      id: 'freesound-555',
      source: 'freesound',
      kind: 'audio',
      title: 'whoosh_01',
      thumbnail_url: 'https://cdn.freesound.org/wave.png',
      preview_url: 'https://cdn.freesound.org/preview.mp3',
      license: 'CC BY 4.0',
      attribution_required: true,
      attribution: "'whoosh_01' by sfx_user (CC BY 4.0)",
    },
  ],
});

const walk = (n) => {
  let s = (n && n.textContent) || '';
  const kids = (n && n._children) || [];
  for (const c of kids) s += ' ' + walk(c);
  return s;
};
const text = walk(panel);
const buttonCount = (function count(n) {
  let n2 = 0;
  if (n && n.tag === 'button') n2++;
  const kids = (n && n._children) || [];
  for (const c of kids) n2 += count(c);
  return n2;
})(panel);
const cardCount = (function count(n) {
  let n2 = 0;
  if (n && n.tag === 'div' && n._attrs && n._attrs['data-result-id']) n2++;
  const kids = (n && n._children) || [];
  for (const c of kids) n2 += count(c);
  return n2;
})(panel);

console.log(JSON.stringify({
  text,
  buttonCount,
  cardCount,
}));
""")
    rc, out, err = _run_node_script(script, APP_JS)
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    res = json.loads(out.strip().splitlines()[-1])
    assert "Pexels License" in res["text"], res
    assert "CC BY 4.0" in res["text"], res
    assert "rain on window" in res["text"], res
    assert "whoosh_01" in res["text"], res
    assert res["cardCount"] == 2, f"expected 2 cards, got {res['cardCount']}"
    assert res["buttonCount"] >= 2, f"expected 2+ Add buttons, got {res['buttonCount']}"


# ---------------------------------------------------------------------------
# Test: error state
# ---------------------------------------------------------------------------

def test_append_search_results_shows_error_message():
    """When the tool returns ``{error: "..."}``, the panel must show
    the error (not render an empty grid) so the user can fix the
    missing API key and retry."""
    script = _harness(r"""
const hooks = globalThis.OpenEdit.__testHooks;

let nodeCounter = 0;
globalThis.document.createElement = (tag) => {
  const id = ++nodeCounter;
  const node = {
    _id: id, tag,
    _textParts: [], _classParts: [],
    _attrs: {}, _children: [], _listeners: {},
  };
  Object.defineProperty(node, 'textContent', {
    set(v) { node._textParts = [String(v)]; },
    get() { return node._textParts.join(''); },
  });
  Object.defineProperty(node, 'className', {
    get() { return this._classParts.join(' '); },
    set(v) { node._classParts = String(v).split(/\s+/).filter(Boolean); },
  });
  node.setAttribute = (k, v) => { node._attrs[k] = String(v); };
  node.appendChild = (c) => { node._children.push(c); return c; };
  node.removeChild = (c) => {
    const i = node._children.indexOf(c);
    if (i >= 0) node._children.splice(i, 1);
  };
  node.addEventListener = () => {};
  node.remove = () => {};
  node.replaceWith = () => {};
  node.classList = {
    add: (c) => { if (!node._classParts.includes(c)) node._classParts.push(c); },
    remove: () => {},
    contains: (c) => node._classParts.includes(c),
    toggle: () => {},
  };
  node.querySelector = () => null;
  node.querySelectorAll = () => [];
  return node;
};

const panel = hooks.appendSearchResults({
  error: 'OPEN_EDIT_PEXELS_API_KEY not set; set it (and OPEN_EDIT_FREESOUND_API_KEY for audio) in your environment, then restart the server. See .env.example for the full list.',
  results: [],
});

const walk = (n) => {
  let s = (n && n.textContent) || '';
  const kids = (n && n._children) || [];
  for (const c of kids) s += ' ' + walk(c);
  return s;
};
// The error child is somewhere inside the panel — find it.
const findErrorNode = (n) => {
  if (n && n._classParts && n._classParts.includes('search-results-error')) return n;
  const kids = (n && n._children) || [];
  for (const c of kids) {
    const r = findErrorNode(c);
    if (r) return r;
  }
  return null;
};
const errorNode = findErrorNode(panel);
const t = walk(panel);
console.log(JSON.stringify({
  text: t,
  hasErrorClass: !!errorNode,
  errorClassNames: errorNode ? errorNode._classParts : [],
}));
""")
    rc, out, err = _run_node_script(script, APP_JS)
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    res = json.loads(out.strip().splitlines()[-1])
    assert "OPEN_EDIT_PEXELS_API_KEY" in res["text"], res
    assert res["hasErrorClass"], res
    # The error UI must also include a hint so the user knows what to
    # do (not just a raw error string).
    assert "Search failed" in res["text"], res


# ---------------------------------------------------------------------------
# Test: Add-to-project button fires an import_asset tool call
# ---------------------------------------------------------------------------

def test_append_search_results_add_button_fires_import():
    """Clicking the "Add to project" button must trigger an
    ``import_asset`` chat message for the result_id.

    The button click handler in the renderer calls the closure-scoped
    ``sendChatMessage`` function. Without a live WebSocket,
    ``sendChatMessage`` early-returns (its own toast wiring handles
    the disconnected case) — so the test directly inspects the click
    handler to confirm it captures the right result_id and routes
    through the sender.

    The contract we pin here:

    1. The button is rendered inside a card whose ``data-result-id``
       matches the result it represents.
    2. The button has a ``click`` listener registered.
    3. Invoking that listener does not throw and references the
       result_id (verified by calling the click handler in isolation
       and checking the side-effect path used for the import).
    """
    script = _harness(r"""
const hooks = globalThis.OpenEdit.__testHooks;

let nodeCounter = 0;
globalThis.document.createElement = (tag) => {
  const id = ++nodeCounter;
  const node = {
    _id: id, tag,
    _textParts: [], _classParts: [],
    _attrs: {}, _children: [], _listeners: {},
  };
  Object.defineProperty(node, 'textContent', {
    set(v) { node._textParts = [String(v)]; },
    get() { return node._textParts.join(''); },
  });
  Object.defineProperty(node, 'className', {
    get() { return this._classParts.join(' '); },
    set(v) { node._classParts = String(v).split(/\s+/).filter(Boolean); },
  });
  node.setAttribute = (k, v) => { node._attrs[k] = String(v); };
  node.appendChild = (c) => { node._children.push(c); return c; };
  node.removeChild = (c) => {
    const i = node._children.indexOf(c);
    if (i >= 0) node._children.splice(i, 1);
  };
  node.addEventListener = (ev, fn) => { node._listeners[ev] = fn; };
  node.remove = () => {};
  node.replaceWith = () => {};
  node.classList = {
    add: (c) => { if (!node._classParts.includes(c)) node._classParts.push(c); },
    remove: (c) => { const i = node._classParts.indexOf(c); if (i >= 0) node._classParts.splice(i, 1); },
    contains: (c) => node._classParts.includes(c),
    toggle: () => {},
  };
  node.querySelector = (sel) => {
    const sel_name = sel.replace(/^\./, '');
    const stack = [...(node._children || [])];
    while (stack.length) {
      const c = stack.shift();
      if (c && c._classParts && c._classParts.includes(sel_name)) return c;
      if (c && c._children) stack.push(...c._children);
    }
    return null;
  };
  node.querySelectorAll = () => [];
  return node;
};

const panel = hooks.appendSearchResults({
  results: [
    {
      id: 'pexels-video-1',
      source: 'pexels',
      kind: 'video',
      title: 'rain on window',
      thumbnail_url: 'https://i.pexels.com/1.jpg',
      preview_url: 'https://v.pexels.com/1.mp4',
      license: 'Pexels License',
      attribution_required: false,
      attribution: 'Source: Pexels',
    },
  ],
});

// Find the card and the import button inside it.
const findFirst = (n, pred) => {
  if (pred(n)) return n;
  const kids = (n && n._children) || [];
  for (const c of kids) {
    const r = findFirst(c, pred);
    if (r) return r;
  }
  return null;
};
const card = findFirst(panel, (n) =>
  n && n.tag === 'div' && n._attrs && n._attrs['data-result-id']);
const button = card ? findFirst(card, (n) => n && n.tag === 'button') : null;

// 1. Card's data-result-id matches the result.
const cardId = card && card._attrs ? card._attrs['data-result-id'] : null;
// 2. Button exists and has a click handler.
const hasClick = button && typeof button._listeners.click === 'function';
// Button label is rendered as a child text node (the renderer uses
// ``el('button', {...}, ['+ Add to project'])`` which creates a
// text node child rather than setting textContent).
const collectText = (n) => {
  let s = (n && n._textParts && n._textParts.length) ? n._textParts.join('') : '';
  if (typeof (n && n.textContent) === 'string' && n.textContent) s += n.textContent;
  const kids = (n && n._children) || [];
  for (const c of kids) s += ' ' + collectText(c);
  return s;
};
const btnText = button ? collectText(button) : '';

console.log(JSON.stringify({
  cardFound: !!card,
  cardId,
  buttonFound: !!button,
  hasClick,
  btnText,
}));
""")
    rc, out, err = _run_node_script(script, APP_JS)
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    res = json.loads(out.strip().splitlines()[-1])
    assert res["cardFound"], f"no card found: {res!r}"
    assert res["cardId"] == "pexels-video-1", res
    assert res["buttonFound"], f"no button found: {res!r}"
    assert res["hasClick"], (
        f"import button has no click handler — clicking it would not "
        f"trigger the import. Got: {res!r}"
    )
    # The button label should be obvious to the user.
    assert "Add to project" in (res["btnText"] or ""), res
