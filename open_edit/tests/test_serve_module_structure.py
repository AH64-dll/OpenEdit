"""Test the v1.4 P2 ES module structure is intact.

The brief: "Add a Node-sandbox test that loads the new module
structure and verifies the ``__testHooks`` namespace is intact."

The frontend is split into six ES modules under
``open_edit/serve/static/js/`` (state, dom, api, assets, chat, ws),
loaded via ``<script type="module" src="/app.js">``. The entry
point assembles them and exposes a ``window.OpenEdit.__testHooks``
namespace the Node-sandbox tests in this directory depend on.

This test pins the *contract* of the module structure — the list
of hooks the entry point exposes — so a refactor that accidentally
drops or renames one fails loudly here instead of as a confusing
error in a downstream test file.

What we check:

1. The entry-point module loads without throwing (the harness in
   ``tests/_node_harness.py`` already does this; we re-assert
   here so the test reads as a self-contained module-structure
   contract).
2. ``window.OpenEdit.__testHooks`` exists and is an object.
3. Every hook the existing per-feature tests depend on is
   present and is a function. We list the exact keys so a missing
   hook shows up as a precise diff, not a generic "undefined".
4. The supporting ``window.OpenEdit`` namespace also exposes the
   higher-level helpers (``loadProjectState``, ``selectProject``,
   ``refreshProjects``) the loading-state tests drive.

The list is intentionally narrow — see the comment in
``app.js``'s ``window.OpenEdit = { ... }`` block for the same
discipline. A hook is added here only when a test needs it; this
test pins the current set so a future PR that removes one without
updating the test list sees a clear failure.
"""
from __future__ import annotations

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


# The exact set of hooks the test suite depends on. If you add a
# hook, add it here AND in ``app.js``'s ``__testHooks`` block. If
# you remove one, remove the corresponding test file first.
EXPECTED_TEST_HOOKS = [
    # State normalizers (P0-2: normalizeAssets url passthrough; the
    # rest are used by the asset-stream test's regression checks).
    "normalizeAssets",
    "normalizeEdits",
    "normalizeTimeline",
    "normalizeRenders",
    "normalizeNotes",
    "summarizeOpPayload",
    # Asset panel (P0-2: openAssetPreview annotates title when no url).
    "openAssetPreview",
    # Chat status indicator (P1-2: state machine).
    "createChatStatus",
    # Cost badge (P1-3: state machine).
    "createCostBadge",
    # Search-assets results panel (P1-1: renderer).
    "appendSearchResults",
    # Chat sender (P1-1: the search-results "Add to project" button
    # sends an import_asset message through this).
    "sendChatMessage",
]

# The high-level helpers the loading-state tests drive. These are
# NOT under __testHooks — they live at the top level of
# ``window.OpenEdit`` so the in-browser console can call them too.
EXPECTED_OPENEDIT_HELPERS = [
    "loadProjectState",
    "selectProject",
    "refreshProjects",
    "connectWS",
    "state",
    "api",
]


def test_module_loads_and_exposes_test_hooks():
    """The entry-point ES module loads cleanly and exposes the
    full ``__testHooks`` namespace the test suite depends on.
    """
    # Build the expected set as JSON for the test body to compare
    # against (so the test reports a precise diff if a hook is
    # missing, not a generic ``undefined``).
    import json
    expected_hooks = json.dumps(EXPECTED_TEST_HOOKS)
    expected_helpers = json.dumps(EXPECTED_OPENEDIT_HELPERS)

    script = _harness(r"""
const expectedHooks = __EXPECTED_HOOKS__;
const expectedHelpers = __EXPECTED_HELPERS__;

// 1. window.OpenEdit exists (the harness already imported the
//    module, so a failure here is a regression in the import).
if (typeof globalThis.OpenEdit !== 'object' || globalThis.OpenEdit === null) {
  console.error('NO_OPENEDIT');
  process.exit(2);
}

// 2. __testHooks exists and is an object.
const hooks = globalThis.OpenEdit.__testHooks;
if (typeof hooks !== 'object' || hooks === null) {
  console.error('NO_TEST_HOOKS');
  process.exit(3);
}

// 3. Every expected hook is present and is a function.
const present = Object.keys(hooks);
const missing = expectedHooks.filter((k) => typeof hooks[k] !== 'function');
if (missing.length) {
  console.error('MISSING_HOOKS:' + missing.join(','));
  process.exit(4);
}

// 4. The supporting helpers are present (not under __testHooks).
const missingHelpers = expectedHelpers.filter((k) => !(k in globalThis.OpenEdit));
if (missingHelpers.length) {
  console.error('MISSING_HELPERS:' + missingHelpers.join(','));
  process.exit(5);
}

console.log(JSON.stringify({
  hooks: present.sort(),
  helpers: expectedHelpers.filter((k) => k in globalThis.OpenEdit).sort(),
}));
""").replace("__EXPECTED_HOOKS__", expected_hooks).replace("__EXPECTED_HELPERS__", expected_helpers)

    rc, out, err = _run_node_script(script, APP_JS)
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    import json
    payload = json.loads(out.strip().splitlines()[-1])
    assert sorted(payload["hooks"]) == sorted(EXPECTED_TEST_HOOKS), (
        f"unexpected hooks present: {payload['hooks']!r}"
    )
    assert sorted(payload["helpers"]) == sorted(EXPECTED_OPENEDIT_HELPERS), (
        f"unexpected helpers: {payload['helpers']!r}"
    )


def test_module_dependencies_resolve():
    """The entry point imports from each sibling module (state,
    dom, api, assets, chat, ws). A typo in any of those import
    paths would break the import, which the harness surfaces as
    an ``IMPORT_FAILED`` exit code. This test pins the
    six-module split — drop or rename a module and the test fails.

    The test re-asserts the import completes successfully (the
    harness in ``_node_harness.py`` exits with code 2 on import
    failure, but it's worth pinning the contract here so the
    module-structure test reads as a complete spec)."""
    script = _harness(r"""
const mod = await import('file://' + process.argv[2]);
// Touch one export from each module to make sure the live
// bindings all resolve. If a sibling module is missing, the
// import above would have failed.
const checks = {
  state: typeof globalThis.OpenEdit.state === 'object' && globalThis.OpenEdit.state !== null,
  api: typeof globalThis.OpenEdit.api === 'object' && globalThis.OpenEdit.api !== null,
  // createChatStatus is from chat.js; createCostBadge is too.
  // openAssetPreview is from assets.js; normalizeAssets is from
  // state.js. If any of those modules failed to import, these
  // hooks would be missing.
  chat_status: typeof globalThis.OpenEdit.__testHooks.createChatStatus === 'function',
  cost_badge: typeof globalThis.OpenEdit.__testHooks.createCostBadge === 'function',
  assets: typeof globalThis.OpenEdit.__testHooks.openAssetPreview === 'function',
  normalizer: typeof globalThis.OpenEdit.__testHooks.normalizeAssets === 'function',
};
console.log(JSON.stringify(checks));
""")
    rc, out, err = _run_node_script(script, APP_JS)
    assert rc == 0, f"rc={rc} stdout={out!r} stderr={err!r}"
    import json
    checks = json.loads(out.strip().splitlines()[-1])
    for k, v in checks.items():
        assert v, f"expected {k} to be importable / present, got: {checks!r}"
