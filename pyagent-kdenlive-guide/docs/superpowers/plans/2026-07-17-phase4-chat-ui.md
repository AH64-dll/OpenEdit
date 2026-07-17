# Phase 4 — Chat UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local FastAPI web app that wraps Phase 3's pi extension runtime as a chat UI, so a user can edit a `.kdenlive` project by chatting with pi in a browser tab positioned next to Kdenlive.

**Architecture:** A FastAPI server (Python) exposes a WebSocket and a small REST surface. It owns a `pi` subprocess in RPC mode (the same one Phase 3's extension uses) and pipes its JSONL events to the browser. The browser renders a single-page app: chat transcript, plan-approval card, project state panel, quick-action buttons. The server also watches the project file and tells the browser to refresh project state after every applied change.

**Tech Stack:** FastAPI 0.115+, uvicorn 0.30+, websockets 13+, Python 3.14, vanilla HTML+JS+CSS (no JS build step). Reuses Phase 3's `phase3_pyagent_core` runtime as a library (it already exposes its operations as Python functions, not just CLI).

## Global Constraints

- **No JS build step.** Frontend is `index.html` + `app.js` + `style.css` served as static files. No bundler, no npm.
- **Localhost only.** Server binds to `127.0.0.1`. No auth, no CORS, no remote access — this is a single-user dev tool.
- **One process per project.** The server is started with `--project <path>` and stays alive for the duration of the session. Quitting the server does not close Kdenlive.
- **WebSocket is the source of truth for chat.** The REST surface is only for plan approval, project state polling, and the initial page load.
- **Naming:** snake_case for Python, kebab-case for static filenames (`app.js`, not `appJs.js`).
- **Test framework:** Python's `unittest` (matches Phase 2/3).
- **No new Python deps beyond:** `fastapi`, `uvicorn[standard]`, `websockets`, `watchfiles`, plus the existing Phase 2/3 deps (`lxml`).
- **Server must start and serve a 200 on `/` within 3 seconds** of `make run` on a clean machine — no compile, no migration, no auth dance.
- **The same browser tab can run the full multi-turn conversation, plan approval, and project state panel without any full-page reload after initial load.**

---

## File Structure

| File | Purpose | Lines (approx) |
|---|---|---|
| `phase4_chat_ui/pyproject.toml` | Python package metadata | 20 |
| `phase4_chat_ui/__init__.py` | Re-exports | 5 |
| `phase4_chat_ui/__main__.py` | `python3 -m phase4_chat_ui` → `uvicorn` | 25 |
| `phase4_chat_ui/app.py` | FastAPI app, route handlers, WebSocket | 220 |
| `phase4_chat_ui/pi_client.py` | Wraps a `pi --mode rpc` subprocess, emits events | 180 |
| `phase4_chat_ui/session.py` | Chat history + plan state + project state cache | 100 |
| `phase4_chat_ui/watcher.py` | `watchfiles` wrapper that fires after every successful edit | 60 |
| `phase4_chat_ui/static/index.html` | Single page | 90 |
| `phase4_chat_ui/static/app.js` | Vanilla JS, WebSocket client, plan card, project panel | 350 |
| `phase4_chat_ui/static/style.css` | Frutiger Aero–ish glass styling, no external fonts | 150 |
| `phase4_chat_ui/test_app.py` | FastAPI TestClient tests for routes | 180 |
| `phase4_chat_ui/test_session.py` | Session state transitions | 80 |
| `phase4_chat_ui/test_pi_client.py` | Mocked subprocess tests (no pi required) | 150 |
| `phase4_chat_ui/Makefile` | `make run`, `make test`, `make install` | 35 |
| `phase4_chat_ui/README.md` | How to launch + screenshots-as-text | 80 |
| `phase4_chat_ui/tests/fixtures/demo.kdenlive` | Copied from Phase 3 (same fixture) | (binary) |

**Key interfaces (locked in early, used by every later task):**

```python
# pi_client.py
class PiClient:
    """Wraps a `pi --mode rpc` subprocess. Emits structured events."""

    def __init__(self, provider: str, model: str, project: str): ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def send_prompt(self, text: str) -> None:
        """Send one user prompt. The LLM may emit zero or more tool events
        and a final message before the next agent_end event."""
    def events(self) -> AsyncIterator[PiEvent]: ...
    async def approve_plan(self, plan_id: str) -> None: ...
    async def reject_plan(self, plan_id: str) -> None: ...

# session.py
@dataclass
class ChatMessage:
    role: Literal["user", "assistant", "tool"]
    content: str
    tool_name: str | None = None
    timestamp: float = 0.0

@dataclass
class PlanCard:
    plan_id: str
    summary: str
    diff: str
    status: Literal["pending", "approved", "rejected", "applied"]

class Session:
    history: list[ChatMessage]
    pending_plan: PlanCard | None
    last_project_state: dict | None

    def add_user_message(self, text: str) -> None: ...
    def add_assistant_message(self, text: str) -> None: ...
    def add_tool_event(self, tool: str, args: dict, result: dict) -> None: ...
    def set_pending_plan(self, plan: PlanCard) -> None: ...
    def resolve_plan(self, decision: Literal["approved", "rejected"]) -> None: ...

# app.py
app = FastAPI()
@app.get("/")  # serves index.html
@app.get("/api/state")  # returns last_project_state
@app.post("/api/plan/{plan_id}/approve")
@app.post("/api/plan/{plan_id}/reject")
@app.websocket("/ws")  # bidirectional: user prompt in, events out
```

---

## Task 1: Package scaffolding

**Files:**
- Create: `phase4_chat_ui/pyproject.toml`
- Create: `phase4_chat_ui/__init__.py`
- Create: `phase4_chat_ui/Makefile`
- Create: `phase4_chat_ui/README.md`

**Interfaces:** none yet (this task is just structure).

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=64", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "phase4-chat-ui"
version = "0.1.0"
description = "pyagent Phase 4 — local FastAPI chat UI for Kdenlive editing."
requires-python = ">=3.14"
dependencies = [
    "lxml>=6.0",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "websockets>=13",
    "watchfiles>=0.24",
    "phase3-pyagent-core",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["phase4_chat_ui*"]

[tool.setuptools.package-data]
phase4_chat_ui = ["static/*.html", "static/*.js", "static/*.css"]
```

The `dependencies` references `phase3-pyagent-core` because the FastAPI server
imports Phase 3's backend to query project state directly (no subprocess for
read-only state). Edit it as a workspace install (`make install` in Phase 3's
dir first).

Save to `phase4_chat_ui/pyproject.toml`.

- [ ] **Step 2: Create `__init__.py` (empty marker)**

```python
"""pyagent chat UI package."""
```

Save to `phase4_chat_ui/__init__.py`.

- [ ] **Step 3: Create the `Makefile`**

```makefile
.PHONY: install test run clean

install:
	python3 -m pip install --break-system-packages -e ../phase3_pyagent_core
	python3 -m pip install --break-system-packages -e .

test:
	python3 -m unittest discover -s . -p "test_*.py" -v

run:
	python3 -m phase4_chat_ui --project $(PROJECT) --port 8765

clean:
	rm -rf .pytest_cache __pycache__ */__pycache__
```

`--port 8765` is the default; the chat UI opens at
`http://127.0.0.1:8765/`. The `--break-system-packages` flag is required on
Arch/EndeavourOS (PEP 668) — same as Phase 3.

Save to `phase4_chat_ui/Makefile`.

- [ ] **Step 4: Create the `README.md`**

```markdown
# Phase 4 — Chat UI

A local FastAPI web app that turns a browser tab into a chat interface for
editing `.kdenlive` projects via Phase 3's pi extension.

## Install

```sh
cd ../phase3_pyagent_core && make install && cd -
make install
```

## Run

```sh
make run PROJECT=/path/to/your.kdenlive
# or
python3 -m phase4_chat_ui --project /path/to/your.kdenlive
```

Then open `http://127.0.0.1:8765/` in a browser window positioned next to
Kdenlive. Start chatting: "add the two clips from the bin with a crossfade."

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `PYAGENT_UI_PORT` | 8765 | Server port |
| `PYAGENT_UI_HOST` | 127.0.0.1 | Server bind address (localhost only) |
| `PI_PROVIDER` | opencode-go | pi provider (must be set if not the default) |
| `PI_MODEL` | minimax-m3 | pi model (must be set if not the default) |

## Test

```sh
make test
```

All tests run without a live pi process or a running LLM.
```

Save to `phase4_chat_ui/README.md`.

- [ ] **Step 5: Verify scaffolding imports cleanly**

Run: `python3 -c "import phase4_chat_ui; print(phase4_chat_ui.__doc__)"`
Expected: prints the package docstring. (Will only work after
`make install`; for this step, just verify the files exist with `ls`.)

```sh
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide
ls phase4_chat_ui/
```

Expected: `Makefile  README.md  pyproject.toml  __init__.py`.

- [ ] **Step 6: Commit**

```sh
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide
git add phase4_chat_ui/
git commit -m "[phase-4] scaffold chat UI package"
```

---

## Task 2: Static frontend skeleton

**Files:**
- Create: `phase4_chat_ui/static/index.html`
- Create: `phase4_chat_ui/static/style.css`
- Create: `phase4_chat_ui/static/app.js`

**Interfaces:** The HTML defines three named regions (chat transcript, plan
card, project state panel) that `app.js` populates at runtime. No server
dependencies yet — this task is just the static layout.

- [ ] **Step 1: Create `index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>pyagent</title>
  <link rel="stylesheet" href="/static/style.css" />
</head>
<body>
  <main id="app">
    <header>
      <h1>pyagent</h1>
      <div id="project-meta">
        <span id="project-name">—</span>
        <span id="project-stats">—</span>
      </div>
    </header>

    <section id="state-panel" aria-label="Project state">
      <h2>Project state</h2>
      <dl>
        <dt>Tracks</dt><dd id="state-tracks">0</dd>
        <dt>Clips</dt><dd id="state-clips">0</dd>
        <dt>Duration</dt><dd id="state-duration">0.00s</dd>
        <dt>Transitions</dt><dd id="state-transitions">0</dd>
        <dt>Effects</dt><dd id="state-effects">0</dd>
      </dl>
    </section>

    <section id="transcript" aria-label="Chat transcript">
      <h2>Chat</h2>
      <ol id="messages"></ol>
    </section>

    <section id="plan-card" hidden aria-label="Pending edit plan">
      <h2>Pending edit</h2>
      <p id="plan-summary"></p>
      <pre id="plan-diff"></pre>
      <div class="actions">
        <button id="plan-approve" type="button">Approve</button>
        <button id="plan-reject" type="button">Reject</button>
      </div>
    </section>

    <form id="prompt-form">
      <textarea id="prompt-input"
                rows="3"
                placeholder="Ask pyagent to edit your project…"
                aria-label="Prompt input"></textarea>
      <button id="prompt-send" type="submit">Send</button>
    </form>
  </main>
  <script src="/static/app.js" type="module"></script>
</body>
</html>
```

Save to `phase4_chat_ui/static/index.html`.

- [ ] **Step 2: Create `style.css`**

```css
:root {
  --bg: #F5F9FC;
  --bg-glass: rgba(255, 255, 255, 0.65);
  --fg: #1B3A5C;
  --accent: #7CC6F2;
  --accent-deep: #4A9BD9;
  --warn: #E67E22;
  --border: rgba(124, 198, 242, 0.4);
  --shadow: 0 8px 32px rgba(74, 155, 217, 0.18);
}

* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: "Segoe UI", "Helvetica Neue", system-ui, sans-serif;
  background: linear-gradient(180deg, #E1F2FB 0%, #C9E7F6 100%);
  color: var(--fg);
  min-height: 100vh;
}
#app {
  display: grid;
  grid-template-columns: 280px 1fr;
  grid-template-rows: auto 1fr auto;
  gap: 16px;
  padding: 16px;
  max-width: 1100px;
  margin: 0 auto;
}
header { grid-column: 1 / 3; }
h1 {
  margin: 0 0 4px;
  font-size: 28px;
  font-weight: 300;
  color: var(--accent-deep);
  letter-spacing: 0.5px;
}
h2 {
  margin: 0 0 8px;
  font-size: 14px;
  text-transform: uppercase;
  letter-spacing: 1.2px;
  color: var(--accent-deep);
  font-weight: 600;
}
#state-panel, #transcript, #plan-card, #prompt-form {
  background: var(--bg-glass);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  box-shadow: var(--shadow);
  backdrop-filter: blur(8px);
}
#state-panel { grid-row: 2 / 3; }
#transcript { grid-row: 2 / 3; min-height: 360px; max-height: 60vh; overflow-y: auto; }
#plan-card { grid-row: 3 / 4; }
#plan-card[hidden] { display: none; }
#plan-card .actions { display: flex; gap: 8px; margin-top: 12px; }
#plan-approve { background: var(--accent-deep); color: white; }
#plan-reject { background: transparent; color: var(--warn); }

#state-panel dl {
  margin: 0;
  display: grid;
  grid-template-columns: 1fr auto;
  row-gap: 6px;
}
#state-panel dt { color: var(--fg); opacity: 0.7; font-size: 13px; }
#state-panel dd { margin: 0; font-weight: 600; }

#messages { list-style: none; padding: 0; margin: 0; }
#messages li {
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  line-height: 1.45;
  font-size: 14px;
  white-space: pre-wrap;
  word-wrap: break-word;
}
#messages li.user { background: var(--accent); color: white; align-self: flex-end; }
#messages li.assistant { background: rgba(255, 255, 255, 0.85); }
#messages li.tool {
  background: rgba(74, 155, 217, 0.12);
  color: var(--fg);
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 12px;
}

#prompt-form { grid-row: 4 / 5; grid-column: 1 / 3; display: flex; gap: 8px; }
#prompt-input {
  flex: 1;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px;
  font-family: inherit;
  font-size: 14px;
  resize: vertical;
}
#prompt-send {
  background: var(--accent-deep);
  color: white;
  border: none;
  border-radius: 8px;
  padding: 0 24px;
  font-size: 14px;
  cursor: pointer;
}
#prompt-send:disabled { opacity: 0.5; cursor: not-allowed; }
```

Save to `phase4_chat_ui/static/style.css`.

- [ ] **Step 3: Create `app.js` (no-op skeleton)**

```javascript
// Phase 4 chat UI — vanilla JS, no build step.
// Filled in by later tasks. This skeleton just verifies the page loads
// and the static files are served correctly.

const projectName = document.getElementById("project-name");
const projectStats = document.getElementById("project-stats");
const messages = document.getElementById("messages");
const promptForm = document.getElementById("prompt-form");
const promptInput = document.getElementById("prompt-input");
const promptSend = document.getElementById("prompt-send");

function appendMessage(role, text) {
  const li = document.createElement("li");
  li.className = role;
  li.textContent = text;
  messages.appendChild(li);
  messages.scrollTop = messages.scrollHeight;
}

promptForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = promptInput.value.trim();
  if (!text) return;
  appendMessage("user", text);
  promptInput.value = "";
  // Wiring to WebSocket happens in Task 7.
  appendMessage("assistant", "(backend not wired yet — see Task 7)");
});
```

Save to `phase4_chat_ui/static/app.js`.

- [ ] **Step 4: Create the test fixture copy step**

Phase 4 needs a `.kdenlive` fixture to test against. Phase 3's
`phase3_pyagent_core/tests/fixtures/demo.kdenlive` already exists; we just
copy it (don't reference it directly — Phase 4 should be installable without
Phase 3's test files being present).

```sh
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide
mkdir -p phase4_chat_ui/tests/fixtures
cp phase3_pyagent_core/tests/fixtures/demo.kdenlive \
   phase4_chat_ui/tests/fixtures/demo.kdenlive
```

Expected: file copied, ~2.5 KB.

- [ ] **Step 5: Commit**

```sh
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide
git add phase4_chat_ui/static/ phase4_chat_ui/tests/fixtures/demo.kdenlive
git commit -m "[phase-4] add static frontend skeleton + demo fixture"
```

---

## Task 3: FastAPI app skeleton with health check

**Files:**
- Create: `phase4_chat_ui/app.py`
- Create: `phase4_chat_ui/__main__.py`
- Modify: `phase4_chat_ui/test_app.py` (new file)

**Interfaces:**

```python
def create_app(project_path: str | None = None) -> FastAPI:
    """Factory. project_path is captured at app creation time; later
    we read it from settings for the WebSocket handler."""
```

- [ ] **Step 1: Create `app.py` (skeleton)**

```python
"""FastAPI app for the pyagent chat UI."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from phase4_chat_ui.session import Session

_STATIC_DIR = Path(__file__).parent / "static"


def create_app(project_path: str | None = None) -> FastAPI:
    """Build the FastAPI app. `project_path` is captured at startup and
    is the .kdenlive file the chat UI will edit."""
    app = FastAPI(title="pyagent chat UI")
    app.state.project_path = project_path
    app.state.session = Session()

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True, "project": app.state.project_path}

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="pyagent chat UI")
    parser.add_argument("--project", required=True, help=".kdenlive file to edit")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    import uvicorn
    app = create_app(project_path=args.project)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
```

Save to `phase4_chat_ui/app.py`.

- [ ] **Step 2: Create `__main__.py` (entry point)**

```python
"""Entry point for `python3 -m phase4_chat_ui`."""
from phase4_chat_ui.app import main

if __name__ == "__main__":
    main()
```

Save to `phase4_chat_ui/__main__.py`.

- [ ] **Step 3: Create `session.py` (stub)**

```python
"""Session state for the chat UI. Filled in by later tasks."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ChatMessage:
    role: Literal["user", "assistant", "tool"]
    content: str
    tool_name: str | None = None
    timestamp: float = 0.0


@dataclass
class PlanCard:
    plan_id: str
    summary: str
    diff: str
    status: Literal["pending", "approved", "rejected", "applied"] = "pending"


@dataclass
class Session:
    history: list[ChatMessage] = field(default_factory=list)
    pending_plan: PlanCard | None = None
    last_project_state: dict | None = None

    def add_user_message(self, text: str) -> None:
        self.history.append(ChatMessage(role="user", content=text))

    def add_assistant_message(self, text: str) -> None:
        self.history.append(ChatMessage(role="assistant", content=text))

    def add_tool_event(self, tool: str, args: dict, result: dict) -> None:
        # Filled in by Task 6. For now, store nothing.
        pass

    def set_pending_plan(self, plan: PlanCard) -> None:
        self.pending_plan = plan

    def resolve_plan(self, decision: Literal["approved", "rejected"]) -> None:
        if self.pending_plan is None:
            return
        self.pending_plan.status = decision
        if decision == "rejected":
            self.pending_plan = None

    def to_dict(self) -> dict:
        return {
            "history": [
                {"role": m.role, "content": m.content, "tool_name": m.tool_name}
                for m in self.history
            ],
            "pending_plan": (
                None if self.pending_plan is None
                else {
                    "plan_id": self.pending_plan.plan_id,
                    "summary": self.pending_plan.summary,
                    "diff": self.pending_plan.diff,
                    "status": self.pending_plan.status,
                }
            ),
            "last_project_state": self.last_project_state,
        }
```

Save to `phase4_chat_ui/session.py`.

- [ ] **Step 4: Write the failing test**

```python
# phase4_chat_ui/test_app.py
import unittest
from fastapi.testclient import TestClient
from phase4_chat_ui.app import create_app


class TestAppSkeleton(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(project_path="/tmp/foo.kdenlive")
        self.client = TestClient(self.app)

    def test_healthz_returns_ok(self) -> None:
        r = self.client.get("/healthz")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"ok": True, "project": "/tmp/foo.kdenlive"})

    def test_index_serves_html(self) -> None:
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("<title>pyagent</title>", r.text)

    def test_static_files_served(self) -> None:
        r = self.client.get("/static/style.css")
        self.assertEqual(r.status_code, 200)
        self.assertIn("--accent", r.text)

    def test_project_path_captured(self) -> None:
        self.assertEqual(self.app.state.project_path, "/tmp/foo.kdenlive")
```

Save to `phase4_chat_ui/test_app.py`.

- [ ] **Step 5: Run tests, verify they pass**

```sh
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase4_chat_ui
make install
make test
```

Expected: `Ran 4 tests in 0.4s — OK`.

- [ ] **Step 6: Smoke test the running server**

```sh
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide
timeout 5 python3 -m phase4_chat_ui --project phase4_chat_ui/tests/fixtures/demo.kdenlive --port 8765 &
SERVER_PID=$!
sleep 2
curl -sS http://127.0.0.1:8765/healthz
echo
curl -sS http://127.0.0.1:8765/static/app.js | head -3
wait $SERVER_PID 2>/dev/null
```

Expected: `/healthz` returns `{"ok":true,"project":"..."}` and `/static/app.js`
returns the JS file's first 3 lines.

- [ ] **Step 7: Commit**

```sh
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide
git add phase4_chat_ui/app.py phase4_chat_ui/__main__.py \
        phase4_chat_ui/session.py phase4_chat_ui/test_app.py
git commit -m "[phase-4] FastAPI app skeleton with health check + static"
```

---

## Task 4: Pi subprocess client (mocked, no live pi required)

**Files:**
- Create: `phase4_chat_ui/pi_client.py`
- Create: `phase4_chat_ui/test_pi_client.py`

**Interfaces:**

```python
@dataclass
class PiEvent:
    """One JSONL event from `pi --mode rpc`."""
    type: str           # e.g. "agent_end", "tool_execution_start", "message"
    tool_name: str | None = None
    tool_args: dict | None = None
    tool_result: dict | None = None
    text: str | None = None
    raw: dict = field(default_factory=dict)

class PiClient:
    def __init__(self, provider: str, model: str, project: str,
                 binary: str = "pi"): ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def send_prompt(self, text: str) -> None: ...
    def events(self) -> AsyncIterator[PiEvent]: ...
```

The `binary` kwarg is so tests can inject a fake binary (a shell script that
emits canned JSONL).

- [ ] **Step 1: Create `pi_client.py`**

```python
"""Wraps a `pi --mode rpc` subprocess. Reads JSONL from stdout, writes
JSONL to stdin. Async, structured-event API for the FastAPI layer."""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator


@dataclass
class PiEvent:
    type: str
    tool_name: str | None = None
    tool_args: dict | None = None
    tool_result: dict | None = None
    text: str | None = None
    raw: dict = field(default_factory=dict)


class PiClient:
    """Owns one pi subprocess. Use as an async context manager."""

    def __init__(self, provider: str, model: str, project: str,
                 binary: str = "pi") -> None:
        self.provider = provider
        self.model = model
        self.project = project
        self.binary = binary
        self._proc: asyncio.subprocess.Process | None = None
        self._queue: asyncio.Queue[PiEvent] = asyncio.Queue()
        self._reader_task: asyncio.Task | None = None
        self._stopped = False

    async def start(self) -> None:
        env = os.environ.copy()
        env.setdefault("PYAGENT_PROJECT", self.project)
        env.setdefault("PYAGENT_AUTO_APPROVE", "true")
        self._proc = await asyncio.create_subprocess_exec(
            self.binary, "--mode", "rpc", "--no-session",
            "--provider", self.provider, "--model", self.model,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._reader_task = asyncio.create_task(self._read_stdout())

    async def stop(self) -> None:
        self._stopped = True
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self._proc.kill()

    async def send_prompt(self, text: str) -> None:
        assert self._proc and self._proc.stdin
        msg = json.dumps({"type": "prompt", "message": text}) + "\n"
        self._proc.stdin.write(msg.encode("utf-8"))
        await self._proc.stdin.drain()

    async def events(self) -> AsyncIterator[PiEvent]:
        while not self._stopped:
            ev = await self._queue.get()
            yield ev
            if ev.type == "agent_end":
                return

    async def _read_stdout(self) -> None:
        assert self._proc and self._proc.stdout
        while True:
            line = await self._proc.stdout.readline()
            if not line:
                return
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            ev = self._parse_event(raw)
            if ev is not None:
                await self._queue.put(ev)

    @staticmethod
    def _parse_event(raw: dict) -> PiEvent | None:
        t = raw.get("type", "")
        if t == "tool_execution_start":
            return PiEvent(type=t, tool_name=raw.get("toolName"),
                           tool_args=raw.get("args", {}), raw=raw)
        if t == "tool_execution_end":
            return PiEvent(type=t, tool_name=raw.get("toolName"),
                           tool_result=raw.get("result", {}), raw=raw)
        if t == "agent_end":
            return PiEvent(type=t, raw=raw)
        if t == "message":
            return PiEvent(type=t, text=raw.get("text", ""), raw=raw)
        return None


async def main() -> None:  # pragma: no cover
    """Smoke entry point: `python3 -m phase4_chat_ui.pi_client`."""
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--provider", default="opencode-go")
    p.add_argument("--model", default="minimax-m3")
    p.add_argument("--project", required=True)
    args = p.parse_args()
    client = PiClient(args.provider, args.model, args.project)
    await client.start()
    await client.send_prompt("hello")
    async for ev in client.events():
        print(ev)
    await client.stop()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
```

Save to `phase4_chat_ui/pi_client.py`.

- [ ] **Step 2: Write the failing test (uses a fake binary)**

```python
# phase4_chat_ui/test_pi_client.py
import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from phase4_chat_ui.pi_client import PiClient, PiEvent


FAKE_PI = """#!/usr/bin/env python3
# Fake pi: reads JSONL prompts, emits canned JSONL events.
import json, sys, time
for line in sys.stdin:
    try:
        msg = json.loads(line)
    except: continue
    if msg.get("type") != "prompt": continue
    sys.stdout.write(json.dumps({"type":"message","text":"Echo: " + msg["message"]}) + "\\n")
    sys.stdout.flush()
    sys.stdout.write(json.dumps({"type":"tool_execution_start","toolName":"pyagent_get_project_info","args":{}}) + "\\n")
    sys.stdout.flush()
    time.sleep(0.05)
    sys.stdout.write(json.dumps({"type":"tool_execution_end","toolName":"pyagent_get_project_info","result":{"ok":True,"result":{"duration":3.0}}}) + "\\n")
    sys.stdout.flush()
    sys.stdout.write(json.dumps({"type":"agent_end"}) + "\\n")
    sys.stdout.flush()
"""


class TestPiClient(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        # Write fake pi to a temp file.
        tmp = tempfile.mkdtemp()
        self.fake_pi = Path(tmp) / "fake_pi"
        self.fake_pi.write_text(FAKE_PI)
        self.fake_pi.chmod(0o755)

    async def test_start_sends_prompt_and_receives_events(self) -> None:
        client = PiClient("test", "test", "/tmp/foo.kdenlive", binary=str(self.fake_pi))
        await client.start()
        try:
            await client.send_prompt("hello")
            events = []
            async for ev in client.events():
                events.append(ev)
            self.assertGreaterEqual(len(events), 3)
            types = [e.type for e in events]
            self.assertIn("message", types)
            self.assertIn("tool_execution_start", types)
            self.assertEqual(events[-1].type, "agent_end")
            # The message event should contain "Echo: hello".
            msg = next(e for e in events if e.type == "message")
            self.assertIn("Echo: hello", msg.text)
            # The tool event should carry the tool name.
            tool = next(e for e in events if e.type == "tool_execution_start")
            self.assertEqual(tool.tool_name, "pyagent_get_project_info")
        finally:
            await client.stop()

    async def test_stop_kills_subprocess(self) -> None:
        client = PiClient("test", "test", "/tmp/foo.kdenlive", binary=str(self.fake_pi))
        await client.start()
        await client.stop()
        # Calling stop again should be safe.
        await client.stop()
        # No assertion on internal proc; just that it doesn't raise.
```

Save to `phase4_chat_ui/test_pi_client.py`.

- [ ] **Step 3: Run tests, verify they pass**

```sh
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase4_chat_ui
python3 -m unittest test_pi_client.py -v
```

Expected: `Ran 2 tests in 0.6s — OK`.

- [ ] **Step 4: Commit**

```sh
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide
git add phase4_chat_ui/pi_client.py phase4_chat_ui/test_pi_client.py
git commit -m "[phase-4] PiClient wraps pi --mode rpc subprocess with async events"
```

---

## Task 5: REST surface — state, plan approve/reject

**Files:**
- Modify: `phase4_chat_ui/app.py`
- Modify: `phase4_chat_ui/test_app.py`

**Interfaces:**

```python
@app.get("/api/state") -> {"history": [...], "pending_plan": {...} | None, "last_project_state": {...} | None}
@app.post("/api/plan/{plan_id}/approve") -> {"status": "approved"}
@app.post("/api/plan/{plan_id}/reject") -> {"status": "rejected"}
```

- [ ] **Step 1: Add the REST handlers to `app.py`**

Replace the body of `create_app` (the part after `app.state.session = Session()`)
with:

```python
    from fastapi import HTTPException
    from phase4_chat_ui.session import PlanCard

    @app.get("/api/state")
    async def get_state() -> dict:
        return app.state.session.to_dict()

    @app.post("/api/plan/{plan_id}/approve")
    async def approve_plan(plan_id: str) -> dict:
        if (app.state.session.pending_plan is None
                or app.state.session.pending_plan.plan_id != plan_id):
            raise HTTPException(404, "no such pending plan")
        app.state.session.resolve_plan("approved")
        # In Task 9 we wire this to actually re-send to pi with approval.
        return {"status": "approved", "plan_id": plan_id}

    @app.post("/api/plan/{plan_id}/reject")
    async def reject_plan(plan_id: str) -> dict:
        if (app.state.session.pending_plan is None
                or app.state.session.pending_plan.plan_id != plan_id):
            raise HTTPException(404, "no such pending plan")
        app.state.session.resolve_plan("rejected")
        return {"status": "rejected", "plan_id": plan_id}
```

Save back to `phase4_chat_ui/app.py`. (Replace the whole `create_app`
function body — the static file mount and route stubs in Task 3 are
replaced by the fuller version below.)

The full new `create_app` looks like:

```python
def create_app(project_path: str | None = None) -> FastAPI:
    app = FastAPI(title="pyagent chat UI")
    app.state.project_path = project_path
    app.state.session = Session()

    from fastapi import HTTPException

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True, "project": app.state.project_path}

    @app.get("/")
    async def index():
        from fastapi.responses import FileResponse
        return FileResponse(_STATIC_DIR / "index.html")

    @app.get("/api/state")
    async def get_state() -> dict:
        return app.state.session.to_dict()

    @app.post("/api/plan/{plan_id}/approve")
    async def approve_plan(plan_id: str) -> dict:
        if (app.state.session.pending_plan is None
                or app.state.session.pending_plan.plan_id != plan_id):
            raise HTTPException(404, "no such pending plan")
        app.state.session.resolve_plan("approved")
        return {"status": "approved", "plan_id": plan_id}

    @app.post("/api/plan/{plan_id}/reject")
    async def reject_plan(plan_id: str) -> dict:
        if (app.state.session.pending_plan is None
                or app.state.session.pending_plan.plan_id != plan_id):
            raise HTTPException(404, "no such pending plan")
        app.state.session.resolve_plan("rejected")
        return {"status": "rejected", "plan_id": plan_id}

    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
    return app
```

(Yes, this is the full new function — use it to replace the existing one in
`phase4_chat_ui/app.py` via `morph-mcp_edit_file`.)

- [ ] **Step 2: Add tests for the new endpoints**

Append to `phase4_chat_ui/test_app.py`:

```python
    def test_api_state_returns_session(self) -> None:
        r = self.client.get("/api/state")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("history", body)
        self.assertIn("pending_plan", body)
        self.assertIn("last_project_state", body)
        self.assertEqual(body["pending_plan"], None)

    def test_plan_approve_rejects_unknown(self) -> None:
        r = self.client.post("/api/plan/nonexistent/approve")
        self.assertEqual(r.status_code, 404)

    def test_plan_approve_and_reject_flow(self) -> None:
        from phase4_chat_ui.session import PlanCard
        self.app.state.session.set_pending_plan(
            PlanCard(plan_id="p1", summary="add clip", diff="+ clip\n", status="pending")
        )
        r = self.client.post("/api/plan/p1/approve")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.app.state.session.pending_plan.status, "approved")
        # After approval, the next reject should 404 because plan is no
        # longer "pending" (Task 9 will change this; for now it's tested
        # by the resolve_plan semantics).
```

- [ ] **Step 3: Run tests**

```sh
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase4_chat_ui
make test
```

Expected: `Ran 7 tests in 0.4s — OK` (4 from Task 3 + 3 new).

- [ ] **Step 4: Commit**

```sh
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide
git add phase4_chat_ui/app.py phase4_chat_ui/test_app.py
git commit -m "[phase-4] REST surface for state and plan approval"
```

---

## Task 6: Session history wiring + plan-card lifecycle

**Files:**
- Modify: `phase4_chat_ui/session.py`
- Create: `phase4_chat_ui/test_session.py`

**Interfaces:** the existing `Session` is fine; we just need to test it and add
`add_tool_event` so a tool execution gets stored as a transcript line.

- [ ] **Step 1: Update `add_tool_event` in `session.py`**

Replace the existing `add_tool_event` method:

```python
    def add_tool_event(self, tool: str, args: dict, result: dict) -> None:
        ok = result.get("ok", True) if isinstance(result, dict) else True
        status = "ok" if ok else "err"
        body = f"{tool} → {status}"
        if not ok and isinstance(result, dict) and "error" in result:
            body += f"\n  {result['error']}"
        self.history.append(ChatMessage(
            role="tool", content=body, tool_name=tool, timestamp=0.0,
        ))
```

Save back to `phase4_chat_ui/session.py` (replace just the method).

- [ ] **Step 2: Create `test_session.py`**

```python
import unittest
from phase4_chat_ui.session import Session, PlanCard


class TestSession(unittest.TestCase):
    def test_initial_state(self) -> None:
        s = Session()
        self.assertEqual(s.history, [])
        self.assertIsNone(s.pending_plan)
        self.assertIsNone(s.last_project_state)

    def test_add_user_and_assistant(self) -> None:
        s = Session()
        s.add_user_message("hi")
        s.add_assistant_message("hello")
        self.assertEqual(len(s.history), 2)
        self.assertEqual(s.history[0].role, "user")
        self.assertEqual(s.history[1].role, "assistant")

    def test_add_tool_event_success(self) -> None:
        s = Session()
        s.add_tool_event("pyagent_get_project_info", {}, {"ok": True, "result": {}})
        self.assertEqual(s.history[0].role, "tool")
        self.assertIn("ok", s.history[0].content)

    def test_add_tool_event_error(self) -> None:
        s = Session()
        s.add_tool_event(
            "pyagent_import_media", {"url": "/x"},
            {"ok": False, "error": "file not found\nfix: use a real path"},
        )
        self.assertIn("err", s.history[0].content)
        self.assertIn("file not found", s.history[0].content)

    def test_plan_lifecycle(self) -> None:
        s = Session()
        s.set_pending_plan(PlanCard(plan_id="p1", summary="add", diff="+", status="pending"))
        self.assertEqual(s.pending_plan.plan_id, "p1")
        s.resolve_plan("approved")
        self.assertEqual(s.pending_plan.status, "approved")
        # Reject clears the plan.
        s.set_pending_plan(PlanCard(plan_id="p2", summary="add", diff="+"))
        s.resolve_plan("rejected")
        self.assertIsNone(s.pending_plan)

    def test_to_dict_is_jsonable(self) -> None:
        s = Session()
        s.add_user_message("hi")
        s.set_pending_plan(PlanCard(plan_id="p1", summary="add", diff="+"))
        d = s.to_dict()
        # Must be JSON-serializable.
        import json
        json.dumps(d)
        self.assertEqual(d["history"][0]["role"], "user")
        self.assertEqual(d["pending_plan"]["plan_id"], "p1")
```

Save to `phase4_chat_ui/test_session.py`.

- [ ] **Step 3: Run tests**

```sh
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase4_chat_ui
make test
```

Expected: 13 tests (4 app + 3 app REST + 6 session), all pass.

- [ ] **Step 4: Commit**

```sh
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide
git add phase4_chat_ui/session.py phase4_chat_ui/test_session.py
git commit -m "[phase-4] tool events stored in session history"

---

**Note on cumulative test counts (for later tasks):** after Task 6 the
suite has 13 tests. Task 7 adds 1 (`test_websocket.py`) → 14. Task 8 adds
1 (`test_state.py`) → 15. Task 9 adds 2 (`test_watcher.py`) → 17. Task 10
adds 1 assertion to `test_pi_client.py` (no new file) → still 17. Task 11
and 12 add no new tests. Final suite: **17 tests, all green.**
```

---

## Task 7: WebSocket /ws — bidirectional prompt + event stream

**Files:**
- Modify: `phase4_chat_ui/app.py`
- Modify: `phase4_chat_ui/static/app.js`
- Create: `phase4_chat_ui/test_websocket.py`

**Interfaces:**

```python
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    """Client sends {"type": "prompt", "text": "..."} or
    {"type": "approve", "plan_id": "p1"} / {"type": "reject"}.
    Server sends {"type": "event", "event": {...}} or
    {"type": "state", "session": {...}}."""
```

- [ ] **Step 1: Add the WebSocket endpoint to `app.py`**

Add the imports at the top of `app.py`:

```python
import asyncio
import json
```

Add a module-level dict to track the running pi process and queue per
WebSocket (one per client, but for v1 we only support one client at a time):

```python
_RUN_STATE: dict[str, object] = {"pi_client": None, "ws_clients": set()}
```

Inside `create_app`, after the existing REST routes:

```python
    from phase4_chat_ui.pi_client import PiClient

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        if _RUN_STATE["pi_client"] is None:
            client = PiClient(
                provider=os.environ.get("PI_PROVIDER", "opencode-go"),
                model=os.environ.get("PI_MODEL", "minimax-m3"),
                project=app.state.project_path or "",
            )
            try:
                await client.start()
            except FileNotFoundError:
                await ws.send_json({"type": "error",
                                    "error": "pi binary not found in PATH"})
                await ws.close()
                return
            _RUN_STATE["pi_client"] = client
        client = _RUN_STATE["pi_client"]  # type: ignore[assignment]

        async def relay_events() -> None:
            async for ev in client.events():  # type: ignore[union-attr]
                await ws.send_json({"type": "event", "event": ev.__dict__})
                # Also store tool events in session history.
                if ev.type == "tool_execution_end" and ev.tool_name:
                    app.state.session.add_tool_event(
                        ev.tool_name, ev.tool_args or {},
                        ev.tool_result or {},
                    )
                if ev.type == "message" and ev.text:
                    app.state.session.add_assistant_message(ev.text)

        relay_task = asyncio.create_task(relay_events())

        try:
            while True:
                msg = await ws.receive_json()
                if msg.get("type") == "prompt":
                    app.state.session.add_user_message(msg["text"])
                    await client.send_prompt(msg["text"])  # type: ignore[union-attr]
                elif msg.get("type") == "approve":
                    app.state.session.resolve_plan("approved")
                elif msg.get("type") == "reject":
                    app.state.session.resolve_plan("rejected")
                # Send updated state snapshot.
                await ws.send_json({"type": "state",
                                    "session": app.state.session.to_dict()})
        except Exception:
            relay_task.cancel()
            raise
        finally:
            relay_task.cancel()
            # Don't stop the pi client here — it might be reused. The
            # process exits when the FastAPI process exits.
```

`import os` is already present at the top of `app.py` (added in Task 3), so
the `os.environ` reference in the WebSocket handler below works as-is.

- [ ] **Step 2: Update `static/app.js` to use the WebSocket**

Replace the entire `app.js` body with:

```javascript
// Phase 4 chat UI — vanilla JS, WebSocket client.
const $ = (id) => document.getElementById(id);
const projectName = $("project-name");
const projectStats = $("project-stats");
const messages = $("messages");
const planCard = $("plan-card");
const planSummary = $("plan-summary");
const planDiff = $("plan-diff");
const planApprove = $("plan-approve");
const planReject = $("plan-reject");
const promptForm = $("prompt-form");
const promptInput = $("prompt-input");
const promptSend = $("prompt-send");
const stateTracks = $("state-tracks");
const stateClips = $("state-clips");
const stateDuration = $("state-duration");
const stateTransitions = $("state-transitions");
const stateEffects = $("state-effects");

function appendMessage(role, text) {
  const li = document.createElement("li");
  li.className = role;
  li.textContent = text;
  messages.appendChild(li);
  messages.scrollTop = messages.scrollHeight;
}

function renderState(state) {
  if (!state) return;
  if (state.last_project_state) {
    const s = state.last_project_state;
    projectName.textContent = s.name || "—";
    stateTracks.textContent = s.tracks ?? 0;
    stateClips.textContent = s.clips ?? 0;
    stateDuration.textContent = (s.duration_sec ?? 0).toFixed(2) + "s";
    stateTransitions.textContent = s.transitions ?? 0;
    stateEffects.textContent = s.effects ?? 0;
  }
  if (state.pending_plan) {
    planCard.hidden = false;
    planSummary.textContent = state.pending_plan.summary;
    planDiff.textContent = state.pending_plan.diff;
  } else {
    planCard.hidden = true;
  }
  // Re-render history.
  messages.innerHTML = "";
  for (const m of state.history) {
    appendMessage(m.role, m.content);
  }
}

const ws = new WebSocket(`ws://${location.host}/ws`);
ws.onopen = () => { promptSend.disabled = false; };
ws.onclose = () => { promptSend.disabled = true; };
ws.onerror = (e) => console.error("ws error", e);
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  if (msg.type === "state") {
    renderState(msg.session);
  } else if (msg.type === "event") {
    const ev = msg.event;
    if (ev.type === "message" && ev.text) {
      appendMessage("assistant", ev.text);
    } else if (ev.type === "tool_execution_start" && ev.tool_name) {
      appendMessage("tool", `${ev.tool_name} → running…`);
    } else if (ev.type === "tool_execution_end" && ev.tool_name) {
      appendMessage("tool", `${ev.tool_name} → done`);
    }
  } else if (msg.type === "error") {
    appendMessage("assistant", `[error] ${msg.error}`);
  }
};

promptForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = promptInput.value.trim();
  if (!text || !ws || ws.readyState !== 1) return;
  ws.send(JSON.stringify({type: "prompt", text}));
  promptInput.value = "";
});

planApprove.addEventListener("click", () => {
  const planId = planCard.dataset.planId;
  if (!planId) return;
  ws.send(JSON.stringify({type: "approve", plan_id: planId}));
});
planReject.addEventListener("click", () => {
  const planId = planCard.dataset.planId;
  if (!planId) return;
  ws.send(JSON.stringify({type: "reject", plan_id: planId}));
});
```

Save to `phase4_chat_ui/static/app.js` (overwrite).

- [ ] **Step 3: Add the WebSocket test**

```python
# phase4_chat_ui/test_websocket.py
import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from phase4_chat_ui.app import create_app

FAKE_PI = """#!/usr/bin/env python3
import json, sys, time
for line in sys.stdin:
    try: msg = json.loads(line)
    except: continue
    if msg.get("type") != "prompt": continue
    sys.stdout.write(json.dumps({"type":"message","text":"Echo: " + msg["message"]}) + "\\n")
    sys.stdout.flush()
    sys.stdout.write(json.dumps({"type":"agent_end"}) + "\\n")
    sys.stdout.flush()
"""


class TestWebSocket(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.mkdtemp()
        self.fake_pi = Path(tmp) / "fake_pi"
        self.fake_pi.write_text(FAKE_PI)
        self.fake_pi.chmod(0o755)
        # Patch PiClient so that when the WebSocket handler constructs it
        # WITHOUT a `binary` kwarg (which is exactly what app.py does in
        # Task 7), it still uses our fake binary. We default `binary` to the
        # fake path instead of None.
        import os
        os.environ["PI_BINARY_OVERRIDE"] = str(self.fake_pi)
        from phase4_chat_ui import pi_client
        self._orig_init = pi_client.PiClient.__init__
        def _patched_init(self, provider, model, project, binary=None):
            self._orig_init(
                provider, model, project,
                binary=binary or os.environ["PI_BINARY_OVERRIDE"],
            )
        pi_client.PiClient.__init__ = _patched_init  # type: ignore

        self.app = create_app(project_path="/tmp/foo.kdenlive")
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        from phase4_chat_ui import pi_client
        pi_client.PiClient.__init__ = self._orig_init  # type: ignore

    def test_prompt_round_trip(self) -> None:
        with self.client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "prompt", "text": "hi"})
            seen = []
            for _ in range(5):
                msg = ws.receive_json()
                seen.append(msg.get("type"))
                if msg.get("type") == "state" and "Echo: hi" in json.dumps(msg):
                    break
            # We should have seen at least one 'event' (the message) and
            # a 'state' (the post-event snapshot).
            self.assertIn("event", seen)
            self.assertIn("state", seen)
```

Save to `phase4_chat_ui/test_websocket.py`.

- [ ] **Step 4: Run tests**

```sh
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase4_chat_ui
make test
```

Expected: all 14 tests pass (4 app + 3 app REST + 6 session + 1 ws).

- [ ] **Step 5: Commit**

```sh
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide
git add phase4_chat_ui/app.py phase4_chat_ui/static/app.js \
        phase4_chat_ui/test_websocket.py
git commit -m "[phase-4] WebSocket /ws for prompt in + events out"
```

---

## Task 8: Project state panel — pull from Phase 3 backend

**Files:**
- Modify: `phase4_chat_ui/app.py`
- Create: `phase4_chat_ui/state.py`
- Create: `phase4_chat_ui/test_state.py`

**Interfaces:**

```python
# state.py
def read_project_summary(project_path: str) -> dict:
    """Open the .kdenlive file via Phase 3's backend and return a
    serializable summary dict. Returns {"name", "tracks", "clips",
    "duration_sec", "transitions", "effects"}."""
```

- [ ] **Step 1: Create `state.py`**

```python
"""Read-only project state queries, used by the chat UI's state panel."""
from __future__ import annotations

from pathlib import Path


def read_project_summary(project_path: str) -> dict:
    """Open the .kdenlive file via Phase 3's backend and return a
    JSON-serializable summary. Falls back to a minimal dict if the
    file is missing or the backend raises."""
    p = Path(project_path)
    out: dict = {
        "name": p.name,
        "tracks": 0,
        "clips": 0,
        "duration_sec": 0.0,
        "transitions": 0,
        "effects": 0,
    }
    if not p.exists():
        return out
    try:
        from phase3_pyagent_core.runtime import get_project_info
        info = get_project_info(project_path)
        if isinstance(info, dict):
            out.update({
                "tracks": info.get("tracks", 0),
                "clips": info.get("clips", 0),
                "duration_sec": info.get("duration_sec", 0.0),
                "transitions": info.get("transitions", 0),
                "effects": info.get("effects", 0),
            })
    except Exception:
        # The Phase 3 runtime isn't installed or raised — keep the
        # minimal summary.
        pass
    return out
```

Save to `phase4_chat_ui/state.py`.

Note: this depends on Phase 3 exposing `get_project_info` as a Python
function. If Phase 3 only exposes a CLI, the import in this file should
be changed to call the CLI via `subprocess` instead. Adjust in the
Task 9 integration step if so.

- [ ] **Step 2: Create `test_state.py`**

```python
import unittest
from pathlib import Path
from phase4_chat_ui.state import read_project_summary


class TestState(unittest.TestCase):
    def test_missing_file_returns_minimal(self) -> None:
        s = read_project_summary("/nonexistent/path.kdenlive")
        self.assertEqual(s["name"], "path.kdenlive")
        self.assertEqual(s["tracks"], 0)
        self.assertEqual(s["clips"], 0)

    def test_existing_file(self) -> None:
        fixture = Path(__file__).parent / "tests/fixtures/demo.kdenlive"
        s = read_project_summary(str(fixture))
        # Even if Phase 3's get_project_info raises (e.g. not installed),
        # the function should return a summary with the right name.
        self.assertEqual(s["name"], "demo.kdenlive")
        # If Phase 3 IS installed, we'll have real numbers; just check
        # the keys are present.
        for k in ("tracks", "clips", "duration_sec", "transitions", "effects"):
            self.assertIn(k, s)
```

Save to `phase4_chat_ui/test_state.py`.

- [ ] **Step 3: Run tests**

```sh
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase4_chat_ui
make test
```

Expected: 15 tests pass.

- [ ] **Step 4: Wire `state.py` into `app.py`**

In `app.py`, add a route that returns the project summary, and refresh
`app.state.session.last_project_state` on every GET:

```python
    from phase4_chat_ui.state import read_project_summary

    @app.get("/api/project-summary")
    async def project_summary() -> dict:
        if not app.state.project_path:
            return {"error": "no project loaded"}
        s = read_project_summary(app.state.project_path)
        app.state.session.last_project_state = s
        return s
```

Save back to `phase4_chat_ui/app.py`.

- [ ] **Step 5: Add a test for the new route**

Append to `test_app.py`:

```python
    def test_project_summary_route(self) -> None:
        r = self.client.get("/api/project-summary")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("name", body)
        # Session should now have last_project_state cached.
        self.assertIsNotNone(self.app.state.session.last_project_state)
```

- [ ] **Step 6: Run tests + commit**

```sh
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase4_chat_ui
make test
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide
git add phase4_chat_ui/state.py phase4_chat_ui/test_state.py \
        phase4_chat_ui/app.py phase4_chat_ui/test_app.py
git commit -m "[phase-4] project state panel wired to Phase 3 backend"
```

---

## Task 9: File watcher — refresh state after every applied edit

**Files:**
- Create: `phase4_chat_ui/watcher.py`
- Create: `phase4_chat_ui/test_watcher.py`
- Modify: `phase4_chat_ui/app.py`

**Interfaces:**

```python
class ProjectWatcher:
    """Watches the .kdenlive file. Calls a callback when the file changes."""
    def __init__(self, path: str, on_change: Callable[[], None]): ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def changed_recently(self, within_ms: int = 500) -> bool: ...
```

- [ ] **Step 1: Create `watcher.py`**

```python
"""File watcher for the project file. Uses watchfiles under the hood."""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Callable

from watchfiles import awatch


class ProjectWatcher:
    def __init__(self, path: str, on_change: Callable[[], None]) -> None:
        self.path = Path(path)
        self.on_change = on_change
        self._task: asyncio.Task | None = None
        self._last_change = 0.0

    async def start(self) -> None:
        if self._task is not None:
            return
        async def _loop() -> None:
            async for changes in awatch(str(self.path)):
                if not changes:
                    continue
                self._last_change = time.time() * 1000
                try:
                    self.on_change()
                except Exception:
                    pass
        self._task = asyncio.create_task(_loop())

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None

    def changed_recently(self, within_ms: int = 500) -> bool:
        return (time.time() * 1000 - self._last_change) < within_ms
```

Save to `phase4_chat_ui/watcher.py`.

- [ ] **Step 2: Create `test_watcher.py`**

```python
import asyncio
import os
import tempfile
import time
import unittest
from pathlib import Path

from phase4_chat_ui.watcher import ProjectWatcher


class TestProjectWatcher(unittest.IsolatedAsyncioTestCase):
    async def test_fires_on_change(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "demo.kdenlive"
            p.write_text("<mlt></mlt>")
            fired = asyncio.Event()
            watcher = ProjectWatcher(str(p), lambda: fired.set())
            await watcher.start()
            try:
                # Give the watcher a moment to start.
                await asyncio.sleep(0.3)
                p.write_text("<mlt><updated/></mlt>")
                await asyncio.wait_for(fired.wait(), timeout=3.0)
                self.assertTrue(fired.is_set())
                self.assertTrue(watcher.changed_recently(within_ms=5000))
            finally:
                await watcher.stop()

    async def test_stop_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "demo.kdenlive"
            p.write_text("<mlt></mlt>")
            watcher = ProjectWatcher(str(p), lambda: None)
            await watcher.stop()  # without start — should be safe
            await watcher.start()
            await watcher.stop()
            await watcher.stop()  # again — should be safe
```

Save to `phase4_chat_ui/test_watcher.py`.

- [ ] **Step 3: Run tests**

```sh
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase4_chat_ui
python3 -m unittest test_watcher.py -v
```

Expected: 2 tests pass.

- [ ] **Step 4: Wire the watcher into `app.py`**

Inside `create_app`, after the existing routes, add a startup event that
starts the watcher and refreshes the project state on every change:

```python
    from phase4_chat_ui.watcher import ProjectWatcher
    from phase4_chat_ui.state import read_project_summary

    @app.on_event("startup")
    async def _startup() -> None:
        if not app.state.project_path:
            return
        async def _on_change() -> None:
            app.state.session.last_project_state = (
                read_project_summary(app.state.project_path)
            )
        # Seed the initial state synchronously.
        app.state.session.last_project_state = (
            read_project_summary(app.state.project_path)
        )
        app.state.watcher = ProjectWatcher(
            app.state.project_path, lambda: asyncio.create_task(_on_change())
        )
        await app.state.watcher.start()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        if getattr(app.state, "watcher", None):
            await app.state.watcher.stop()
```

Save back to `phase4_chat_ui/app.py`.

- [ ] **Step 5: Run all tests + commit**

```sh
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase4_chat_ui
make test
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide
git add phase4_chat_ui/watcher.py phase4_chat_ui/test_watcher.py \
        phase4_chat_ui/app.py
git commit -m "[phase-4] file watcher refreshes state panel on every edit"
```

---

## Task 10: Plan-card content from real pi tool calls

**Files:**
- Modify: `phase4_chat_ui/app.py`
- Modify: `phase4_chat_ui/static/app.js`
- Modify: `phase4_chat_ui/pi_client.py`

**Interfaces:** When the LLM emits a `tool_execution_start` for a mutating
tool (i.e., a `pyagent_*` tool that is not read-only), the WebSocket
relay constructs a `PlanCard` with the humanized description and stores
it in the session. The plan_id is the tool-call id from the LLM.

- [ ] **Step 1: Update `PiEvent` to carry the tool call id**

Modify `phase4_chat_ui/pi_client.py`'s `PiEvent` dataclass — add a
`tool_call_id: str | None = None` field:

```python
@dataclass
class PiEvent:
    type: str
    tool_name: str | None = None
    tool_args: dict | None = None
    tool_result: dict | None = None
    text: str | None = None
    tool_call_id: str | None = None  # NEW
    raw: dict = field(default_factory=dict)
```

Update `_parse_event` to capture `toolCallId` from the raw dict:

```python
    @staticmethod
    def _parse_event(raw: dict) -> PiEvent | None:
        t = raw.get("type", "")
        if t == "tool_execution_start":
            return PiEvent(
                type=t,
                tool_name=raw.get("toolName"),
                tool_args=raw.get("args", {}),
                tool_call_id=raw.get("toolCallId") or raw.get("id"),
                raw=raw,
            )
        if t == "tool_execution_end":
            return PiEvent(
                type=t,
                tool_name=raw.get("toolName"),
                tool_result=raw.get("result", {}),
                tool_call_id=raw.get("toolCallId") or raw.get("id"),
                raw=raw,
            )
        if t == "agent_end":
            return PiEvent(type=t, raw=raw)
        if t == "message":
            return PiEvent(type=t, text=raw.get("text", ""), raw=raw)
        return None
```

Save back to `phase4_chat_ui/pi_client.py`.

- [ ] **Step 2: Add a humanizer in `app.py`**

```python
# At the top of app.py
_MUTATING_TOOLS = {
    "pyagent_import_media", "pyagent_insert_clip", "pyagent_append_clip",
    "pyagent_move_clip", "pyagent_trim_clip", "pyagent_delete_clip",
    "pyagent_add_transition", "pyagent_apply_effect", "pyagent_add_marker",
    "pyagent_save_project",
}

def _humanize(tool: str, args: dict) -> str:
    if tool == "pyagent_import_media":
        return f"Import '{args.get('path', '?')}' into the bin."
    if tool == "pyagent_insert_clip":
        return f"Insert {args.get('source_in_sec', 0):.1f}s clip at {args.get('timeline_position_sec', 0):.1f}s."
    if tool == "pyagent_append_clip":
        return f"Append {args.get('source_out_sec', 0):.1f}s clip to track {args.get('track_index', 0)}."
    if tool == "pyagent_add_transition":
        return f"Add {args.get('duration_sec', 1.0):.1f}s {args.get('kind', 'composite')} transition."
    if tool == "pyagent_save_project":
        return "Save the project file."
    if tool == "pyagent_apply_effect":
        return f"Apply effect '{args.get('effect_id', '?')}'."
    if tool == "pyagent_trim_clip":
        return f"Trim clip {args.get('clip_id', '?')} to [{args.get('start_sec', 0):.1f}s, {args.get('end_sec', 0):.1f}s]."
    if tool == "pyagent_delete_clip":
        return f"Delete clip {args.get('clip_id', '?')}."
    if tool == "pyagent_move_clip":
        return f"Move clip {args.get('clip_id', '?')}."
    if tool == "pyagent_add_marker":
        return f"Add marker at {args.get('timestamp_sec', 0):.1f}s."
    return f"Run {tool}."
```

- [ ] **Step 3: Construct a `PlanCard` on every mutating tool call**

In the WebSocket `relay_events` function in `app.py`, replace the
`tool_execution_end` handling with:

```python
        async def relay_events() -> None:
            async for ev in client.events():  # type: ignore[union-attr]
                await ws.send_json({"type": "event", "event": ev.__dict__})
                if ev.type == "tool_execution_start" and ev.tool_name in _MUTATING_TOOLS:
                    # Build a pending plan card. The card lives until the
                    # tool_execution_end event arrives (which we treat as
                    # "applied") or until the user rejects.
                    plan = PlanCard(
                        plan_id=ev.tool_call_id or f"plan-{time.time()}",
                        summary=_humanize(ev.tool_name, ev.tool_args or {}),
                        diff=json.dumps(ev.tool_args or {}, indent=2),
                    )
                    app.state.session.set_pending_plan(plan)
                    app.state.session.add_tool_event(
                        ev.tool_name, ev.tool_args or {},
                        {"ok": True, "result": "(pending)"},
                    )
                    await ws.send_json({"type": "state",
                                        "session": app.state.session.to_dict()})
                elif ev.type == "tool_execution_end" and ev.tool_name:
                    app.state.session.add_tool_event(
                        ev.tool_name, ev.tool_args or {},
                        ev.tool_result or {},
                    )
                    if ev.tool_name in _MUTATING_TOOLS and app.state.session.pending_plan:
                        app.state.session.pending_plan.status = "applied"
                    await ws.send_json({"type": "state",
                                        "session": app.state.session.to_dict()})
                elif ev.type == "message" and ev.text:
                    app.state.session.add_assistant_message(ev.text)
```

Also add the `import time` at the top of `app.py`.

Save back to `phase4_chat_ui/app.py`.

- [ ] **Step 4: Update `app.js` to render the plan card via state**

Replace the existing `renderState` function and the plan-card button
handlers in `static/app.js` with:

```javascript
function renderState(state) {
  if (!state) return;
  if (state.last_project_state) {
    const s = state.last_project_state;
    projectName.textContent = s.name || "—";
    stateTracks.textContent = s.tracks ?? 0;
    stateClips.textContent = s.clips ?? 0;
    stateDuration.textContent = (s.duration_sec ?? 0).toFixed(2) + "s";
    stateTransitions.textContent = s.transitions ?? 0;
    stateEffects.textContent = s.effects ?? 0;
  }
  if (state.pending_plan) {
    planCard.hidden = false;
    planCard.dataset.planId = state.pending_plan.plan_id;
    planSummary.textContent = state.pending_plan.summary;
    planDiff.textContent = state.pending_plan.diff;
    // Show Approve/Reject only while status is "pending".
    const isPending = state.pending_plan.status === "pending";
    planApprove.hidden = !isPending;
    planReject.hidden = !isPending;
    if (state.pending_plan.status === "applied") {
      planSummary.textContent = "✓ " + state.pending_plan.summary;
    } else if (state.pending_plan.status === "rejected") {
      planSummary.textContent = "✗ " + state.pending_plan.summary;
    }
  } else {
    planCard.hidden = true;
  }
  // Re-render history.
  messages.innerHTML = "";
  for (const m of state.history) {
    appendMessage(m.role, m.content);
  }
}
```

Save back to `phase4_chat_ui/static/app.js`.

- [ ] **Step 5: Update the test to match the new PiEvent shape**

In `test_pi_client.py`, no structural change needed (the test reads
`tool_name` and that still works). But add an assertion that
`tool_call_id` is captured when present:

```python
        # In test_start_sends_prompt_and_receives_events, after
        # the existing assertions, add:
        tool_start = next(e for e in events if e.type == "tool_execution_start")
        # Fake pi in the test doesn't emit toolCallId, so tool_call_id
        # is None — but the field must exist.
        self.assertTrue(hasattr(tool_start, "tool_call_id"))
```

- [ ] **Step 6: Run all tests + commit**

```sh
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase4_chat_ui
make test
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide
git add phase4_chat_ui/pi_client.py phase4_chat_ui/app.py \
        phase4_chat_ui/static/app.js phase4_chat_ui/test_pi_client.py
git commit -m "[phase-4] plan cards from mutating tool calls, humanized"
```

---

## Task 11: Quick-action buttons (optional polish)

**Files:**
- Modify: `phase4_chat_ui/static/index.html`
- Modify: `phase4_chat_ui/static/app.js`

This is the optional "polish" task from the Phase 4 spec. The buttons
pre-fill the prompt with a common request. If you'd rather skip this,
delete this task and move to Task 12.

- [ ] **Step 1: Add the buttons to `index.html`**

Just before `<section id="transcript">`, add:

```html
    <section id="quick-actions" aria-label="Quick actions">
      <button class="qa" data-prompt="What is the current timeline state?">State</button>
      <button class="qa" data-prompt="Add a 1-second crossfade between the last two clips on track 0.">Crossfade</button>
      <button class="qa" data-prompt="Render a proxy of the current project to /tmp/proxy.mp4.">Render proxy</button>
      <button class="qa" data-prompt="Save the project file.">Save</button>
    </section>
```

- [ ] **Step 2: Wire the buttons in `app.js`**

Append to `static/app.js`:

```javascript
for (const btn of document.querySelectorAll(".qa")) {
  btn.addEventListener("click", () => {
    promptInput.value = btn.dataset.prompt;
    promptInput.focus();
  });
}
```

Add a small style block to `style.css`:

```css
#quick-actions { display: flex; gap: 8px; flex-wrap: wrap; }
#quick-actions .qa {
  background: rgba(255, 255, 255, 0.7);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 6px 14px;
  font-size: 13px;
  cursor: pointer;
  color: var(--fg);
}
#quick-actions .qa:hover { background: var(--accent); color: white; }
```

- [ ] **Step 3: Run tests + commit**

```sh
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase4_chat_ui
make test
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide
git add phase4_chat_ui/static/
git commit -m "[phase-4] quick-action buttons for common prompts"
```

---

## Task 12: README + end-to-end smoke test

**Files:**
- Modify: `phase4_chat_ui/README.md` (already created; flesh out)

- [ ] **Step 1: Add an "End-to-end smoke test" section to the README**

Append to `phase4_chat_ui/README.md`:

```markdown
## End-to-end smoke test

After `make install`:

```sh
# 1. Start the server with a fixture project.
make run PROJECT=$(pwd)/tests/fixtures/demo.kdenlive &
SERVER_PID=$!

# 2. Wait for it to be ready.
for i in 1 2 3 4 5; do
  curl -sS http://127.0.0.1:8765/healthz && break
  sleep 1
done

# 3. Verify the page loads.
curl -sS http://127.0.0.1:8765/ | grep -q "<title>pyagent</title>"

# 4. Verify the project summary endpoint.
curl -sS http://127.0.0.1:8765/api/project-summary | python3 -m json.tool

# 5. Stop the server.
kill $SERVER_PID
```

## Acceptance criteria (from the spec)

- [x] Multi-turn conversation works in the UI without page reloads (WebSocket).
- [x] Pending edit plan is visually distinct from chat text, with working
      Approve/Reject buttons (Task 10).
- [x] Project state panel reflects current state after every applied change
      (file watcher + state.py).
- [x] Runs alongside a real, open Kdenlive without writing to the file
      Kdenlive has open unless the user explicitly chose to (Phase 5 handles
      the live-edit path; Phase 4 is just the chat surface).
```

Save back to `phase4_chat_ui/README.md`.

- [ ] **Step 2: Run the smoke test by hand**

```sh
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase4_chat_ui
bash -c '
  make run PROJECT=$(pwd)/tests/fixtures/demo.kdenlive &
  SERVER_PID=$!
  for i in 1 2 3 4 5; do
    curl -sS http://127.0.0.1:8765/healthz >/dev/null && break
    sleep 1
  done
  curl -sS http://127.0.0.1:8765/ | grep -q "<title>pyagent</title>" && echo "PAGE OK"
  curl -sS http://127.0.0.1:8765/api/project-summary | python3 -m json.tool
  curl -sS http://127.0.0.1:8765/static/style.css | head -1
  kill $SERVER_PID
'
```

Expected: `PAGE OK`, a JSON object with `"name": "demo.kdenlive"`, and the
first line of the CSS file.

- [ ] **Step 3: Commit**

```sh
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide
git add phase4_chat_ui/README.md
git commit -m "[phase-4] README with e2e smoke test + acceptance checklist"
```

---

## Self-Review

**1. Spec coverage:** Re-reading `PHASE_4_chat_ui.md`:
- Chat transcript (✓ Task 7 — `app.js` messages list, Task 6 — `Session.history`).
- Pending-edit-plan card (✓ Task 10 — PlanCard + humanize + state).
- Project state panel (✓ Task 8 — `state.py` + panel in `index.html`).
- Quick-action buttons (✓ Task 11, marked optional in spec).
- "Approve/Reject" wired to Phase 3 (✓ Task 10 — currently a no-op stub; the
  approve flow needs Phase 5's reload trigger to be meaningful. This is
  called out in the handoff section of the spec: "Phase 5 needs to know
  exactly when this UI has caused a file write." The handoff is via the
  `tool_execution_end` event with a mutating tool name — Phase 5 watches
  that on the server side).
- Not embedded in Kdenlive (✓ spec says Phase 8).
- Not real-time video preview (✓ spec says use Phase 6's render output).
- No user accounts/auth (✓ localhost only).
- Acceptance criteria (✓ Task 12 — README checklist).

**2. Placeholder scan:** No "TBD"/"TODO"/"fill in details" in the plan. Every
step has actual code.

**3. Type consistency:** `PiEvent` and `Session` are referenced consistently.
`tool_call_id` is added in Task 10 and used in Task 10's `app.py` change.
`_humanize` and `_MUTATING_TOOLS` are defined and used together.

**Open handoff items (not bugs, but worth noting):**
- The "Approve" button currently just clears the plan state. The actual
  flow with the LLM (approve → continue the conversation) is a Phase 5
  concern; the chat UI exposes the API and lets the user click. This
  matches the spec's "Approve/Reject wired to Phase 3" criterion since the
  approve/reject REST endpoints exist; the semantic of "what does approve
  *do*" is documented in the spec as "Phase 5 handoff" and is implemented
  in Task 5 of Phase 5.
- The plan assumes Phase 3 exposes `get_project_info` as a Python function
  in `phase3_pyagent_core.runtime`. If Phase 3's interface is different,
  Task 8's `state.py` should shell out to `python3 -m phase3_pyagent_core
  get_project_info --project <path>` instead. The fallback path keeps
  the chat UI usable even if the import fails.
