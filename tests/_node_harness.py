"""Shared harness for the v1.4 Node-sandbox frontend tests.

The frontend (``open_edit/serve/static/app.js``) is an ES module as of
v1.4 P2. Tests that drive it from Node need to:

1. Stub the browser globals (``document``, ``window``, ``localStorage``,
   ``fetch``, ``WebSocket``, ...) on the Node process's ``globalThis``.
   The module code references these as if it were running in a browser.
2. Dynamic-import the module via ``import(pathToFileURL(appPath).href)``.
3. Expose ``window.OpenEdit`` / ``globalThis.OpenEdit`` so the test
   body can drive the test hooks.

The previous pattern (``vm.runInContext``) was used when ``app.js`` was
a single IIFE. Now that ``app.js`` imports its sibling modules
(``state.js``, ``dom.js``, ``api.js``, ``ws.js``, ``chat.js``,
``assets.js``), the sandbox approach no longer fits — ES-module
``import`` statements don't run inside a ``vm`` context. We use Node's
native ``import()`` instead, which resolves module specifiers against
the real file system.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


# The Node script is wrapped in an async IIFE so we can use
# ``await import(...)`` (top-level await requires the file to be an ES
# module, but the temp file is plain ``.js`` and we don't want to
# fiddle with the file extension or package.json).
_HARNESS_TEMPLATE = r"""
'use strict';
(async () => {
  const fs = require('fs');
  const path = require('path');
  const { pathToFileURL } = require('url');

  // --- Browser-like globals --------------------------------------------
  // The ES module's code references ``document``, ``window``,
  // ``localStorage``, ``WebSocket``, ``crypto``, ``fetch``,
  // ``navigator``, ``Response``, ``Node``, ``console``, ``location``
  // — all as if it were a browser script. We stub each on the Node
  // process's ``globalThis`` so the imports resolve. ``window`` is
  // aliased to ``globalThis`` so ``window.OpenEdit = {...}`` from
  // app.js ends up on ``globalThis.OpenEdit`` (which the test body
  // can read).
  //
  // Node 18+ ships with a few of these names (``crypto``, ``fetch``,
  // ``navigator``, ``Response``) as non-writable globals. We use
  // ``Object.defineProperty`` so the stub takes precedence in every
  // Node version the test environment might use.
  const setGlobal = (name, value) => {
    Object.defineProperty(globalThis, name, {
      value, configurable: true, writable: true, enumerable: true,
    });
  };
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
  setGlobal('document', {
    createElement: () => stubElement(),
    createTextNode: (t) => ({ nodeType: 3, textContent: t }),
    addEventListener: () => {},
    querySelector: () => stubElement(),
    querySelectorAll: () => [],
  });
  setGlobal('window', globalThis);
  setGlobal('localStorage', { getItem: () => null, setItem: () => {}, removeItem: () => {} });
  setGlobal('WebSocket', function () { this.close = () => {}; });
  setGlobal('crypto', { randomUUID: () => 'test-uuid' });
  setGlobal('fetch', () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }));
  setGlobal('navigator', { clipboard: { writeText: () => Promise.resolve() } });
  setGlobal('Response', function () {});
  setGlobal('Node', { TEXT_NODE: 3 });
  // Don't override ``console`` — the harness and the test body need
  // to be able to log to stderr. The real console supports the
  // ``.warn`` / ``.error`` / ``.log`` methods the module code uses.
  setGlobal('location', { protocol: 'http:', host: 'localhost' });

  // --- Import the app's ES module --------------------------------------
  const appPath = path.resolve(process.argv[2]);
  const appUrl = pathToFileURL(appPath).href;
  try {
    await import(appUrl);
  } catch (e) {
    console.error('IMPORT_FAILED:', e && (e.stack || e.message || e));
    process.exit(2);
  }

  // --- Test body -------------------------------------------------------
  // The test body has access to:
  //   - All the globals above (document, window, localStorage, ...)
  //   - ``globalThis.OpenEdit`` (set by app.js on boot — well, after
  //     DOMContentLoaded fires; for the test we still need it, so the
  //     app module also sets ``window.OpenEdit = {...}`` at top level
  //     to make the hooks available before any DOM events fire).
  try {
    __TEST_BODY__
  } catch (e) {
    console.error('TEST_FAILED:', e && (e.stack || e.message || e));
    process.exit(1);
  }
})().catch((e) => {
  console.error('HARNESS_FAILED:', e && (e.stack || e.message || e));
  process.exit(3);
});
"""


def harness(script_body: str) -> str:
    """Build a Node script that loads app.js as an ES module into a
    stubbed browser environment, then runs ``script_body``."""
    return _HARNESS_TEMPLATE.replace("__TEST_BODY__", script_body)


def run_node_script(
    script: str, app_js_path: Path, *, timeout: int = 30
) -> tuple[int, str, str]:
    """Write ``script`` to a temp file and run it with Node. The script
    receives the absolute path to app.js as ``argv[2]``. Returns
    ``(returncode, stdout, stderr)``."""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(script)
        path = fh.name
    try:
        proc = subprocess.run(
            ["node", path, str(app_js_path)],
            capture_output=True, text=True, timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    finally:
        os.unlink(path)


def app_js_path() -> Path:
    """The absolute path to the app's entry-point ES module. Resolved
    relative to the mlt-pipeline repo root (two levels up from the
    ``tests/`` directory: ``tests/`` → ``open_edit/`` → the worktree
    root, and one more level to the repo root that hosts the
    ``open_edit/`` package)."""
    return (
        Path(__file__).resolve().parents[2]
        / "open_edit"
        / "open_edit"
        / "serve"
        / "static"
        / "app.js"
    )
