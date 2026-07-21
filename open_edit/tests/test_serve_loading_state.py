"""Tests for the v1.4 P2 loading state on the asset list.

The brief: "Asset list and project switch should show a visible
loading state rather than an empty flash." Before this fix:

- First page load: the HTML default `<div class="empty-state">No
  assets yet.</div>` was visible during the ``getProjectState``
  fetch, then replaced with the real data. The empty state looks
  identical to "this project has no assets," so the user can't
  tell whether the fetch is in flight or has finished.
- Project switch: the OLD project's assets stayed visible during
  the fetch for the NEW project, then suddenly changed. Looks like
  a flicker, not a refresh.

The fix: ``loadProjectState`` shows a centered spinner + "Loading
assets…" message in the assets list while the fetch is in flight.
The next ``renderAssets(...)`` call (with the real data) replaces
it. On error, the loading state is cleared and the toast surfaces
the reason.

These tests pin the spinner-visible-during-fetch contract by
controlling the fetch stub: the test starts a slow request, asserts
the loading state is rendered, then resolves the request and
asserts the loading state is gone and the real data is shown.
"""
from __future__ import annotations

import json
import sys
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
# Shared harness prologue for the loading-state tests
# ---------------------------------------------------------------------------
#
# All three tests below do roughly the same thing:
#   1. Replace ``globalThis.fetch`` with a controllable stub.
#   2. Replace ``globalThis.document.querySelector`` and
#      ``globalThis.document.createElement`` with tracking versions
#      so the test can inspect the loading marker without a real
#      DOM.
#   3. Drive ``loadProjectState`` (or ``selectProject``) and check
#      that the loading marker is (or isn't) visible.
#
# The prologue is the same in every test — only the driver and
# assertions differ. Keeping it inline avoids cross-test state
# leaks (each test runs in its own Node subprocess).
#
# The prologue returns a "snapshot" helper: ``descendantTags`` walks
# the stubbed DOM tree and produces a flat string like
# ``"div.loading-state div.spinner span"`` that the test can grep
# for ``"loading-state"`` and ``"spinner"`` in.

_PROLOGUE = r"""
const OpenEdit = globalThis.OpenEdit;
if (!OpenEdit) { console.error('NO_OPENEDIT'); process.exit(2); }

// --- Tracking document.createElement -----------------------------------
// Produces a node that records its tag, class parts, and children.
// Each test body can read the structure back via the
// ``descendantTags`` helper exposed on the assets-list stub.
globalThis.document.createElement = (tag) => {
  const node = {
    tag,
    _classParts: [],
    _children: [],
    _textContent: '',
    classList: {
      add: (c) => { if (!node._classParts.includes(c)) node._classParts.push(c); },
      remove: (c) => { const i = node._classParts.indexOf(c); if (i >= 0) node._classParts.splice(i, 1); },
      contains: (c) => node._classParts.includes(c),
      toggle: () => {},
    },
    setAttribute: () => {},
    addEventListener: () => {},
    appendChild: (c) => { node._children.push(c); return c; },
    removeChild: (c) => { const i = node._children.indexOf(c); if (i >= 0) node._children.splice(i, 1); },
    replaceWith: () => {},
    remove: () => {},
    querySelector: () => null,
    querySelectorAll: () => [],
    set className(v) { node._classParts = String(v).split(/\s+/).filter(Boolean); },
    get className() { return node._classParts.join(' '); },
    get textContent() { return node._textContent; },
    set textContent(v) { node._textContent = String(v); },
  };
  return node;
};

// --- Assets-list tracker ----------------------------------------------
// The module code calls ``$('#assets-list')`` at runtime and then
// ``list.innerHTML = ''`` / ``list.appendChild(...)``. We track
// every appended child and expose a ``descendantTags`` getter that
// flattens the tree into a single searchable string.
const makeAssetsList = () => {
  let _innerHTML = '';
  let _children = [];
  const el = {
    classList: { add: () => {}, remove: () => {}, toggle: () => {} },
    dataset: {}, style: {}, setAttribute: () => {},
    addEventListener: () => {},
    appendChild: (c) => { _children.push(c); return c; },
    removeChild: (c) => { const i = _children.indexOf(c); if (i >= 0) _children.splice(i, 1); },
    remove() {}, replaceWith: () => {}, click: () => {}, focus: () => {},
    load: () => {}, removeAttribute: () => {},
    querySelector: () => null, querySelectorAll: () => [],
    get innerHTML() { return _innerHTML; },
    set innerHTML(v) {
      _innerHTML = String(v);
      _children = [];
    },
    get descendantTags() {
      const collect = (nodes, out) => {
        for (const c of nodes) {
          if (c && c.tag) {
            const cls = (c._classParts && c._classParts.length)
              ? '.' + c._classParts.join('.') : '';
            out.push(c.tag + cls);
            if (c._children && c._children.length) collect(c._children, out);
          }
        }
        return out;
      };
      return collect(_children, []).join(' ');
    },
    setSeed(html) {
      // Seed the list with a single arbitrary child (for the
      // "old project's data is still there" project-switch test).
      if (html) _children = [Object.assign(globalThis.document.createElement('div'), { className: html })];
    },
  };
  return el;
};

// --- Other element stubs ----------------------------------------------
const makeStubEl = () => ({
  classList: { add: () => {}, remove: () => {}, toggle: () => {} },
  appendChild: () => {}, innerHTML: '', setAttribute: () => {},
  addEventListener: () => {}, removeChild: () => {}, dataset: {},
  textContent: '', value: '', style: {},
  querySelector: () => null, querySelectorAll: () => [],
  removeAttribute: () => {}, load: () => {}, focus: () => {},
  click: () => {}, replaceWith: () => {}, remove: () => {},
  disabled: true,
});

const assetsList = makeAssetsList();
const docStubs = new Map([
  ['#assets-list', assetsList],
  ['#edit-graph-list', makeStubEl()],
  ['#renders-list', makeStubEl()],
  ['#notes-summary', { textContent: '', classList: { add: () => {}, remove: () => {} } }],
  ['#chat-input', { disabled: true, focus: () => {}, addEventListener: () => {}, value: '', style: {} }],
  ['#btn-send', { disabled: true, addEventListener: () => {}, click: () => {} }],
  ['#project-select', { value: '', addEventListener: () => {}, innerHTML: '', appendChild: () => {} }],
  ['#toast', { textContent: '', className: '', classList: { add: () => {} } }],
]);
globalThis.document.querySelector = (sel) => docStubs.get(sel) || makeStubEl();
globalThis.document.querySelectorAll = () => [];
"""


# ---------------------------------------------------------------------------
# Test: loading state is shown while getProjectState is in flight
# ---------------------------------------------------------------------------

def test_load_project_state_shows_loading_marker_during_fetch():
    """While ``api.getProjectState`` is in flight, the assets list
    must show a loading marker (spinner + label) so the user knows
    the data is on its way. This is the "empty flash" the brief
    calls out: before this fix the user saw the previous project's
    stale data (or the HTML default "No assets yet" empty state)
    during the fetch window, with no signal that data was coming.

    The test:
      1. Replaces ``globalThis.fetch`` with a controllable stub
         that returns a never-resolving Promise (we resolve it
         explicitly later).
      2. Calls ``OpenEdit.loadProjectState()``.
      3. Awaits a microtask so the await chain has run far enough
         to set the loading state but not far enough to resolve
         the fetch.
      4. Asserts the assets list shows the loading marker.
      5. Resolves the fetch with a successful payload.
      6. Asserts the assets list now shows the real data and the
         loading marker is gone.
    """
    script = _harness(_PROLOGUE + r"""
let resolveFetch;
const fetchPromise = new Promise((resolve) => { resolveFetch = resolve; });
let fetchCalled = false;
globalThis.fetch = (url) => {
  if (typeof url === 'string' && url.includes('/api/projects/')) {
    fetchCalled = true;
    return fetchPromise;
  }
  return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
};

OpenEdit.state.currentProjectId = 'test-project-1';

const loadPromise = OpenEdit.loadProjectState();
await new Promise((resolve) => setImmediate(resolve));

const loadingSnapshot = assetsList.descendantTags;

resolveFetch({
  ok: true,
  json: () => Promise.resolve({
    assets: [
      { hash: 'h1', filename: 'rain.mp4', duration_s: 12, url: '/api/projects/x/assets/h1/file' },
    ],
  }),
});
await loadPromise;

const finalSnapshot = assetsList.descendantTags;

console.log(JSON.stringify({
  fetchCalled,
  loadingSnapshot,
  finalSnapshot,
}));
""")
    rc, out, err = _run_node_script(script, APP_JS)
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    res = json.loads(out.strip().splitlines()[-1])

    # Fetch was actually called.
    assert res["fetchCalled"], (
        f"loadProjectState did not call fetch; can't verify the loading "
        f"state without a real fetch. Got: {res!r}"
    )

    # During the fetch, the assets list showed a loading marker.
    # The marker is rendered as a .loading-state element with a
    # .spinner inside it and a "Loading assets…" label. We accept
    # any of these tokens as evidence that the loading state was
    # visible — the exact text/class is a UX choice that can evolve.
    loading = res["loadingSnapshot"]
    assert "loading-state" in loading, (
        f"expected a .loading-state marker in the assets list during "
        f"the fetch (the 'empty flash' the brief calls out), got: "
        f"{loading!r}"
    )
    assert "spinner" in loading, (
        f"expected the .loading-state to include a spinner, got: "
        f"{loading!r}"
    )

    # After the fetch resolves, the loading state is gone and the
    # real data is shown.
    final = res["finalSnapshot"]
    assert "loading-state" not in final, (
        f"loading-state should be cleared after the fetch resolves, "
        f"got: {final!r}"
    )
    assert "asset-card" in final, (
        f"expected an .asset-card in the list after the fetch "
        f"resolves, got: {final!r}"
    )


# ---------------------------------------------------------------------------
# Test: loading state is cleared on error (toast surfaces the reason)
# ---------------------------------------------------------------------------

def test_load_project_state_clears_loading_marker_on_error():
    """When ``getProjectState`` fails, the assets list should not be
    stuck on a loading spinner. The error itself is surfaced via
    the existing toast wiring (see P0-1). The list returns to the
    standard empty state so the next successful load has somewhere
    to render into.
    """
    script = _harness(_PROLOGUE + r"""
// Fetch that rejects — the same shape the network would produce on
// a real server error.
globalThis.fetch = (url) => {
  if (typeof url === 'string' && url.includes('/api/projects/')) {
    return Promise.reject(new Error('boom'));
  }
  return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
};

OpenEdit.state.currentProjectId = 'test-project-err';

// Drive the load. The fetch rejects synchronously from the await
// chain, so loadProjectState's catch branch runs and clears the
// loading state.
await OpenEdit.loadProjectState();

const finalSnapshot = assetsList.descendantTags;
console.log(JSON.stringify({ finalSnapshot }));
""")
    rc, out, err = _run_node_script(script, APP_JS)
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    res = json.loads(out.strip().splitlines()[-1])

    # The loading state must be cleared after the error so the list
    # isn't stuck on a spinner.
    final = res["finalSnapshot"]
    assert "loading-state" not in final, (
        f"loading-state should be cleared after a fetch error, got: "
        f"{final!r} (the user would see a stuck spinner with no idea "
        f"what went wrong)"
    )
    # The list returns to the standard empty state so the next
    # successful load has somewhere to render into.
    assert "empty-state" in final, (
        f"expected the assets list to return to its empty state "
        f"after a fetch error, got: {final!r}"
    )


# ---------------------------------------------------------------------------
# Test: project switch shows the loading state (not stale old data)
# ---------------------------------------------------------------------------

def test_project_switch_shows_loading_state_not_stale_data():
    """When the user switches projects, the assets list must NOT
    keep showing the old project's data during the new fetch.
    Before this fix the old project's cards stayed visible (the
    fetch for the new project just appended/overwrote them when
    it landed) — the user saw a confusing "stuck on the old
    project" view while the new one loaded. With the loading
    state, the old data is replaced by a spinner immediately
    on project switch.
    """
    script = _harness(_PROLOGUE + r"""
if (typeof OpenEdit.selectProject !== 'function') {
  console.error('NO_SELECT_PROJECT_HOOK');
  process.exit(2);
}

// Controllable fetch — never resolves during the test.
let resolveFetch;
const fetchPromise = new Promise((resolve) => { resolveFetch = resolve; });
let fetchCount = 0;
globalThis.fetch = (url) => {
  if (typeof url === 'string' && url.includes('/api/projects/')) {
    fetchCount++;
    return fetchPromise;
  }
  return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
};

// Seed the old project's data in the assets list, so we can verify
// the loading state REPLACES the stale data (instead of co-existing
// with it).
assetsList.setSeed('old-movie.mp4');

// Pre-set the current project ID to a different value, so
// ``selectProject('new-project')`` actually triggers a state change
// and a fresh load.
OpenEdit.state.currentProjectId = 'old-project';

// Switch projects. selectProject clears the chat log, updates the
// state, then calls loadProjectState which shows the loading state.
OpenEdit.selectProject('new-project');

// Let the microtask queue drain so the await chain inside
// loadProjectState has run far enough to set the loading state.
await new Promise((resolve) => setImmediate(resolve));

const snapshot = assetsList.descendantTags;
const oldDataStuck = snapshot.includes('old-movie.mp4');

console.log(JSON.stringify({
  fetchCount,
  snapshot,
  oldDataStuck,
}));
""")
    rc, out, err = _run_node_script(script, APP_JS)
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    res = json.loads(out.strip().splitlines()[-1])

    # The fetch was actually triggered.
    assert res["fetchCount"] >= 1, (
        f"selectProject did not trigger a fetch; can't verify the "
        f"loading state. Got: {res!r}"
    )

    # The old project's data is no longer visible — it was replaced
    # by the loading state.
    assert not res["oldDataStuck"], (
        f"old project's data is still showing after the project "
        f"switch — the user would see a confusing mix of old + new. "
        f"Snapshot: {res['snapshot']!r}"
    )

    # And the loading state is visible.
    snapshot = res["snapshot"]
    assert "loading-state" in snapshot, (
        f"expected a .loading-state marker in the assets list "
        f"immediately after the project switch (before the fetch "
        f"resolves), got: {snapshot!r}"
    )
    assert "spinner" in snapshot, (
        f"expected the loading state to include a spinner, got: "
        f"{snapshot!r}"
    )
