# Multi-App Agent Switcher + Per-App Model Picker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a topbar app switcher (PiAgent / OpenCode, Anti-gravity stubbed) and a model dropdown populated from the *selected app's own* model source, switchable at runtime per session and persisted.

**Architecture:** A new `AgentAdapter` abstraction in `phase4_chat_ui/agent_adapters.py` wraps each agentic CLI and yields the existing `PiEvent` shape. `PiAgentAdapter` reuses `PiClient`; `OpenCodeAdapter` shells `opencode run --format json`; `AntiGravityAdapter` is a disabled stub. The FastAPI server holds `app`+`model` in `session_state` and per-socket adapter in `ws_client_map`, recreating the adapter on `set_app`/`set_model` WS messages. The browser renders two topbar `<select>`s from an `/api/apps` payload.

**Tech Stack:** Python 3.14, FastAPI (websockets), `asyncio.subprocess`; `pi` CLI (PiAgent), `opencode` CLI (OpenCode); vanilla JS + HTML + CSS (Frutiger-Aero styling already present).

## Global Constraints

- Godot project context is irrelevant here; this is the PyAgent chat UI (Python/FastAPI).
- All chat-UI code lives under `phase4_chat_ui/`. Agent adapters go in a NEW file `phase4_chat_ui/agent_adapters.py`.
- Reuse the existing `PiEvent` shape (`kind` ∈ {message_delta, thinking, message, tool, plan, error, done}) — OpenCodeAdapter MUST emit the same shape so `relay_event` (app.py) is unchanged.
- Per-app model lists MUST come from each app's own source: PiAgent → `~/.pi/agent/models-store.json` (`opencode-go.models[]`); OpenCode → `opencode models` stdout (`provider/model` per line). No shared hard-coded list.
- Anti-gravity is DISABLED (stub, `available=False`). Do not build live integration.
- Follow existing patterns: snake_case, `asyncio.create_subprocess_exec`, `PYAGENT_PROJECT` env for the extension, `--extension` path loading for PiAgent.
- TDD: each task writes a failing test first, then implements, then commits.

---

### Task 1: `AgentAdapter` protocol + `PiAgentAdapter` (wrap `PiClient`)

**Files:**
- Create: `phase4_chat_ui/agent_adapters.py`
- Modify: none
- Test: `phase4_chat_ui/test_agent_adapters.py` (new)

**Interfaces:**
- Consumes: `PiClient` from `phase4_chat_ui.pi_client` (constructor `PiClient(provider, model, project, binary, session_id, pi_args)`; method `async def run_prompt(text, image_paths) -> AsyncIterator[PiEvent]`; method `stop()`).
- Produces:
  - `class AgentAdapter(Protocol)` with:
    - `app_id: str`
    - `session_id: str` (attribute)
    - `async def run_prompt(self, text: str, image_paths: list[str] | None = None) -> AsyncIterator[PiEvent]`
    - `def list_models(self) -> list[dict]`  (returns `[{"id": str, "name": str}, ...]`)
    - `def stop(self) -> None`
    - `def available(self) -> bool`
  - `class PiAgentAdapter:` implements `AgentAdapter`; `app_id = "piagent"`; `list_models()` reads `~/.pi/agent/models-store.json` → `data["opencode-go"]["models"]` mapped to `{"id": m["id"], "name": m.get("name", m["id"])}`; `available` → `shutil.which("pi") is not None`; `run_prompt` delegates to an internal `PiClient`; `stop` delegates to `self._client.stop()`.

- [ ] **Step 1: Write the failing test**

```python
# phase4_chat_ui/test_agent_adapters.py
from __future__ import annotations
import json
from pathlib import Path
from phase4_chat_ui import agent_adapters as aa


def test_piagent_adapter_list_models(tmp_path, monkeypatch):
    store = {
        "opencode-go": {
            "models": [
                {"id": "minimax-m3", "name": "MiniMax M3"},
                {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro"},
            ]
        }
    }
    p = tmp_path / "models-store.json"
    p.write_text(json.dumps(store))
    monkeypatch.setattr(aa, "MODELS_STORE_PATH", p)
    adapter = aa.PiAgentAdapter(
        model="minimax-m3", project="/x/y.kdenlive",
        session_id="s1", pi_args=[],
    )
    models = adapter.list_models()
    assert models == [
        {"id": "minimax-m3", "name": "MiniMax M3"},
        {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro"},
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && PYTHONPATH=. python3 -m pytest phase4_chat_ui/test_agent_adapters.py::test_piagent_adapter_list_models -v`
Expected: ERROR/FAIL — `ModuleNotFoundError: No module named 'phase4_chat_ui.agent_adapters'`

- [ ] **Step 3: Write minimal implementation**

```python
# phase4_chat_ui/agent_adapters.py
from __future__ import annotations

import json
import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Protocol

from phase4_chat_ui.pi_client import PiClient, PiEvent

MODELS_STORE_PATH = Path(os.path.expanduser("~/.pi/agent/models-store.json"))
_PI_AGENT_PROVIDER = "opencode-go"


class AgentAdapter(Protocol):
    app_id: str
    session_id: str

    async def run_prompt(
        self, text: str, image_paths: list[str] | None = None
    ) -> AsyncIterator[PiEvent]: ...

    def list_models(self) -> list[dict[str, str]]: ...

    def stop(self) -> None: ...

    def available(self) -> bool: ...


class PiAgentAdapter:
    app_id = "piagent"

    def __init__(
        self,
        model: str,
        project: str,
        session_id: str,
        pi_args: list[str] | None = None,
        binary: str | None = None,
        provider: str = _PI_AGENT_PROVIDER,
    ) -> None:
        self.model = model
        self.session_id = session_id
        self._client = PiClient(
            provider=provider,
            model=model,
            project=project,
            binary=binary,
            session_id=session_id,
            pi_args=pi_args if pi_args is not None else [],
        )

    async def run_prompt(self, text, image_paths=None):
        async for ev in self._client.run_prompt(text, image_paths):
            yield ev

    def stop(self) -> None:
        self._client.stop()

    def available(self) -> bool:
        return shutil.which("pi") is not None

    def list_models(self) -> list[dict[str, str]]:
        if not MODELS_STORE_PATH.exists():
            return []
        try:
            data = json.loads(MODELS_STORE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
        models = (
            data.get(_PI_AGENT_PROVIDER, {}).get("models", [])
            if isinstance(data, dict)
            else []
        )
        out: list[dict[str, str]] = []
        for m in models:
            if isinstance(m, dict) and m.get("id"):
                out.append({"id": m["id"], "name": m.get("name", m["id"])})
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && PYTHONPATH=. python3 -m pytest phase4_chat_ui/test_agent_adapters.py::test_piagent_adapter_list_models -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add phase4_chat_ui/agent_adapters.py phase4_chat_ui/test_agent_adapters.py
git commit -m "feat(phase4): add AgentAdapter protocol + PiAgentAdapter wrapping PiClient"
```

---

### Task 2: `OpenCodeAdapter` (shell `opencode run --format json`)

**Files:**
- Modify: `phase4_chat_ui/agent_adapters.py`
- Test: `phase4_chat_ui/test_agent_adapters.py`

**Interfaces:**
- Consumes: `asyncio.create_subprocess_exec`, `PiEvent` (imported from `pi_client`), `shutil.which("opencode")`.
- Produces:
  - `class OpenCodeAdapter:` `app_id = "opencode"`;
    - `list_models()` shells `opencode models` (or uses injected `models_cmd` for tests), parses `provider/model` lines → `[{"id": line.strip(), "name": line.strip()}]` (skip blank lines);
    - `available()` → `shutil.which("opencode") is not None`;
    - `run_prompt(text, image_paths)` launches `opencode run --format json --model <self.model> [--file <img> ...] "<text>"`, reads stdout lines, parses each JSON object, maps to `PiEvent`:
      - `assistant` message with `content` text → `PiEvent(kind="message_delta", role="assistant", text=<text>)`
      - tool_use / function call → `PiEvent(kind="tool", tool=<name>, args=<args>, result=None)`
      - end / result → `PiEvent(kind="done")`
      - error → `PiEvent(kind="error", text=<msg>)`
      - (OpenCode's `--format json` emits raw JSON per event; map the fields it actually emits — capture at least message text, tool calls, and errors. If a field is missing, emit a best-effort `PiEvent`.)
    - `stop()` kills `self._proc` if running.
  - Injectable `models_cmd: list[str]` and `run_cmd: list[str]` (default `["opencode","models"]` / `["opencode","run"]`) so tests don't shell the real binary.

- [ ] **Step 1: Write the failing test**

```python
def test_opencode_adapter_list_models(monkeypatch):
    # capture the command opencode models would run; return fake lines
    captured = {}

    def fake_run(cmd):
        captured["cmd"] = cmd
        return "opencode-go/minimax-m3\nopencode-go/deepseek-v4-pro\n\nopenai/gpt-5.5\n"

    adapter = aa.OpenCodeAdapter(
        model="opencode-go/minimax-m3", project="/x/y.kdenlive",
        session_id="s2", models_cmd_fn=fake_run,
    )
    models = adapter.list_models()
    assert models == [
        {"id": "opencode-go/minimax-m3", "name": "opencode-go/minimax-m3"},
        {"id": "opencode-go/deepseek-v4-pro", "name": "opencode-go/deepseek-v4-pro"},
        {"id": "openai/gpt-5.5", "name": "openai/gpt-5.5"},
    ]
    assert captured["cmd"] == ["opencode", "models"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && PYTHONPATH=. python3 -m pytest phase4_chat_ui/test_agent_adapters.py::test_opencode_adapter_list_models -v`
Expected: FAIL — `AttributeError: module 'phase4_chat_ui.agent_adapters' has no attribute 'OpenCodeAdapter'`

- [ ] **Step 3: Write minimal implementation** (append to `agent_adapters.py`)

```python
class OpenCodeAdapter:
    app_id = "opencode"

    def __init__(
        self,
        model: str,
        project: str,
        session_id: str,
        models_cmd_fn=None,
        run_cmd_fn=None,
    ) -> None:
        self.model = model
        self.project = project
        self.session_id = session_id
        self._models_cmd_fn = models_cmd_fn or self._default_models
        self._run_cmd_fn = run_cmd_fn  # test hook; None -> real subprocess
        self._proc = None

    def available(self) -> bool:
        return shutil.which("opencode") is not None

    def _default_models(self) -> str:
        import subprocess
        try:
            return subprocess.run(
                ["opencode", "models"], capture_output=True, text=True, timeout=20
            ).stdout
        except Exception:
            return ""

    def list_models(self) -> list[dict[str, str]]:
        out = self._models_cmd_fn()
        models: list[dict[str, str]] = []
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            models.append({"id": line, "name": line})
        return models

    async def run_prompt(self, text, image_paths=None):
        cmd = [
            "opencode", "run", "--format", "json",
            "--model", self.model,
        ]
        for ip in (image_paths or []):
            cmd += ["--file", ip]
        cmd += [text]
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert self._proc.stdout is not None
        try:
            async for raw in self._proc.stdout:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                ev = self._to_event(obj)
                if ev is not None:
                    yield ev
            await self._proc.wait()
            yield PiEvent(kind="done")
        except asyncio.CancelledError:
            self.stop()
            raise

    @staticmethod
    def _to_event(obj: dict) -> PiEvent | None:
        t = obj.get("type") or obj.get("role") or ""
        if t == "assistant" or obj.get("role") == "assistant":
            msg = obj.get("message") or obj.get("content") or obj
            text = ""
            if isinstance(msg, dict):
                text = msg.get("content") or msg.get("text") or ""
            elif isinstance(msg, str):
                text = msg
            if text:
                return PiEvent(kind="message_delta", role="assistant", text=str(text))
            return None
        if "tool" in t.lower() or obj.get("tool") or obj.get("toolUse"):
            return PiEvent(
                kind="tool",
                tool=str(obj.get("tool") or obj.get("name") or "tool"),
                args=obj.get("args") or obj.get("input") or {},
                result=None,
            )
        if obj.get("error") or t == "error":
            return PiEvent(kind="error", text=str(obj.get("error") or obj.get("message") or "openCode error"))
        return None

    def stop(self) -> None:
        if self._proc is not None and self._proc.returncode is None:
            try:
                self._proc.kill()
            except Exception:
                pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && PYTHONPATH=. python3 -m pytest phase4_chat_ui/test_agent_adapters.py -v`
Expected: PASS (both Task 1 + Task 2 tests)

- [ ] **Step 5: Commit**

```bash
git add phase4_chat_ui/agent_adapters.py phase4_chat_ui/test_agent_adapters.py
git commit -m "feat(phase4): add OpenCodeAdapter shelling 'opencode run --format json'"
```

---

### Task 3: `AntiGravityAdapter` stub + `build_adapter` / `list_apps`

**Files:**
- Modify: `phase4_chat_ui/agent_adapters.py`
- Test: `phase4_chat_ui/test_agent_adapters.py`

**Interfaces:**
- Produces:
  - `class AntiGravityAdapter:` `app_id = "antigravity"`; `available()` → `False` always; `list_models()` → `[]`; `run_prompt` → immediately `yield PiEvent(kind="error", text="Anti-gravity integration pending")`; `stop()` → `pass`.
  - `def build_adapter(app, model, project, session_id, pi_args=None) -> AgentAdapter`: `"opencode"`→`OpenCodeAdapter`, `"antigravity"`→`AntiGravityAdapter`, else→`PiAgentAdapter(model=model, project=project, session_id=session_id, pi_args=pi_args)`.
  - `def list_apps() -> list[dict]`: returns
    `[{"id": a.app_id, "name": <display>, "available": a.available(), "models": a.list_models()} for a in (PiAgentAdapter(model="", project="", session_id="x"), OpenCodeAdapter(model="", project="", session_id="x"), AntiGravityAdapter(model="", project="", session_id="x"))]`.
    Display names: `piagent`→"PiAgent", `opencode`→"OpenCode", `antigravity`→"Anti-gravity".

- [ ] **Step 1: Write the failing test**

```python
def test_build_adapter_routes():
    assert isinstance(aa.build_adapter("opencode", "opencode-go/minimax-m3", "/x", "s"), aa.OpenCodeAdapter)
    assert isinstance(aa.build_adapter("antigravity", "", "/x", "s"), aa.AntiGravityAdapter)
    assert isinstance(aa.build_adapter("piagent", "minimax-m3", "/x", "s", pi_args=[]), aa.PiAgentAdapter)


def test_list_apps_marks_antigravity_unavailable():
    apps = aa.list_apps()
    by_id = {a["id"]: a for a in apps}
    assert by_id["antigravity"]["available"] is False
    assert by_id["antigravity"]["models"] == []
    # piagent + opencode available on this machine
    assert by_id["piagent"]["available"] is True
    assert by_id["opencode"]["available"] is True
    assert len(by_id["piagent"]["models"]) > 0
    assert len(by_id["opencode"]["models"]) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && PYTHONPATH=. python3 -m pytest phase4_chat_ui/test_agent_adapters.py::test_build_adapter_routes phase4_chat_ui/test_agent_adapters.py::test_list_apps_marks_antigravity_unavailable -v`
Expected: FAIL — `AttributeError: module has no attribute 'AntiGravityAdapter'`

- [ ] **Step 3: Write minimal implementation** (append to `agent_adapters.py`)

```python
class AntiGravityAdapter:
    app_id = "antigravity"

    def __init__(self, model="", project="", session_id="x", **_kw) -> None:
        self.model = model
        self.session_id = session_id

    def available(self) -> bool:
        return False

    def list_models(self) -> list[dict[str, str]]:
        return []

    async def run_prompt(self, text, image_paths=None):
        yield PiEvent(kind="error", text="Anti-gravity integration pending")

    def stop(self) -> None:
        pass


_DISPLAY = {"piagent": "PiAgent", "opencode": "OpenCode", "antigravity": "Anti-gravity"}


def build_adapter(app, model, project, session_id, pi_args=None) -> AgentAdapter:
    if app == "opencode":
        return OpenCodeAdapter(model=model, project=project, session_id=session_id)
    if app == "antigravity":
        return AntiGravityAdapter(model=model, project=project, session_id=session_id)
    return PiAgentAdapter(
        model=model, project=project, session_id=session_id, pi_args=pi_args
    )


def list_apps() -> list[dict]:
    prototypes = [
        PiAgentAdapter(model="", project="", session_id="x"),
        OpenCodeAdapter(model="", project="", session_id="x"),
        AntiGravityAdapter(model="", project="", session_id="x"),
    ]
    return [
        {
            "id": a.app_id,
            "name": _DISPLAY.get(a.app_id, a.app_id),
            "available": a.available(),
            "models": a.list_models(),
        }
        for a in prototypes
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && PYTHONPATH=. python3 -m pytest phase4_chat_ui/test_agent_adapters.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add phase4_chat_ui/agent_adapters.py phase4_chat_ui/test_agent_adapters.py
git commit -m "feat(phase4): add AntiGravityAdapter stub + build_adapter/list_apps"
```

---

### Task 4: Server wiring — `session_state` app/model, `/api/apps`, WS `set_app`/`set_model`, adapter rebuild

**Files:**
- Modify: `phase4_chat_ui/app.py`
- Modify: `phase4_chat_ui/session.py` (add `app`, `model` fields)
- Test: `phase4_chat_ui/test_app.py`

**Interfaces:**
- Consumes (from Task 1-3): `aa.build_adapter(app, model, project, session_id, pi_args)`, `aa.list_apps()`.
- Produces:
  - `create_app(...)` gains `default_app: str = "piagent"` param; `session_state` gains `"app": default_app`.
  - `Session.__init__` gains `app: str = "piagent"`, `model: str = ""`; `to_dict`/`from_dict` persist them; `history_dicts` unaffected.
  - New route `GET /api/apps` → `JSONResponse({"apps": aa.list_apps(), "active_app": session_state["app"], "active_model": session_state["model"]})`.
  - WS connect handshake adds `"apps": aa.list_apps(), "active_app": ..., "active_model": ...` to the initial payload (alongside `"project"`).
  - WS `set_app`: validate `aa.list_apps()` contains id AND `available`; else send `error`. If ok: `session_state["app"]=app`; rebuild `ws_client_map[ws] = aa.build_adapter(app, session_state["model"], current_sess.project, ws_session_map[ws], pi_args)`; cancel in-flight task first (reuse existing `active_tasks` cancel + `await ws_client.stop()`); broadcast `{"type":"app_changed","app":app,"apps":aa.list_apps()}`.
  - WS `set_model`: validate model id is in the active app's `list_models()`; else `error`. If ok: `session_state["model"]=model`; rebuild adapter (same as above); broadcast `{"type":"model_changed","model":model}`.
  - Helper `_rebuild_adapter_for(ws)`: cancels in-flight, builds via `build_adapter(session_state["app"], session_state["model"], sess.project, sess.session_id, pi_args)`, assigns `ws_client_map[ws]`.
  - `switch_session`: after loading, set `session_state`-per-socket adapter from the loaded session's `app`/`model` (rebuild adapter), and include `active_app`/`active_model` in the `session_list`/state broadcast so the UI syncs. (Keep `session_state["app"]` as the global default; per-socket adapter uses the session's stored app/model.)

- [ ] **Step 1: Write the failing test**

```python
# in phase4_chat_ui/test_app.py
def test_set_app_switches_adapter(test_client):
    # test_client is a TestClient with a ws; use the http /api/apps + a ws round-trip
    r = test_client.get("/api/apps")
    assert r.status_code == 200
    body = r.json()
    assert body["active_app"] == "piagent"
    ids = {a["id"] for a in body["apps"]}
    assert ids == {"piagent", "opencode", "antigravity"}
    ag = next(a for a in body["apps"] if a["id"] == "antigravity")
    assert ag["available"] is False
```

(Add a `test_client` fixture if not present; mirror the existing TestClient usage in the file.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && PYTHONPATH=. python3 -m pytest phase4_chat_ui/test_app.py::test_set_app_switches_adapter -v`
Expected: FAIL — 404 or missing `apps` key (no `/api/apps` route yet)

- [ ] **Step 3: Write minimal implementation**

In `app.py`:
1. Add import: `from phase4_chat_ui import agent_adapters as aa`.
2. `create_app` signature: add `default_app: str = "piagent"`, `default_model: str | None = None`. In `session_state` add `"app": default_app` and `"model": default_model or model` (keep existing `model`/provider for PiAgent default).
3. After `default_session` is chosen, ensure `default_session.app`/`default_session.model` default sensibly; store global defaults from `session_state`.
4. Add route:
```python
@app.get("/api/apps")
async def api_apps():
    return JSONResponse({
        "apps": aa.list_apps(),
        "active_app": session_state["app"],
        "active_model": session_state["model"],
    })
```
5. In `ws_endpoint`, after building `client_for_ws = PiClient(...)`, replace with `_rebuild_adapter_for(ws)` pattern (build via `aa.build_adapter`). Add to handshake send_json the `"apps"`, `"active_app"`, `"active_model"` keys.
6. Add `_rebuild_adapter_for(ws)`:
```python
def _rebuild_adapter_for(ws):
    if ws in active_tasks:
        t = active_tasks.pop(ws)
        t.cancel()
        asyncio.create_task(ws_client_map[ws].stop())
    sess_id = ws_session_map.get(ws)
    proj = sessions_cache.get(sess_id).project if sess_id in sessions_cache else project
    ws_client_map[ws] = aa.build_adapter(
        session_state["app"], session_state["model"], proj, sess_id or "x", pi_args,
    )
```
7. In `handle_ws_message`, add handlers:
```python
if mtype == "set_app":
    target = data.get("app")
    apps = {a["id"]: a for a in aa.list_apps()}
    if target not in apps or not apps[target]["available"]:
        await ws.send_json({"type":"error","text":f"App unavailable: {target}"})
        return
    session_state["app"] = target
    _rebuild_adapter_for(ws)
    await manager.broadcast({"type":"app_changed","app":target,"apps":aa.list_apps()})
    return
if mtype == "set_model":
    mid = data.get("model")
    cur = next((a for a in aa.list_apps() if a["id"]==session_state["app"]), None)
    ids = {m["id"] for m in (cur["models"] if cur else [])}
    if mid not in ids:
        await ws.send_json({"type":"error","text":f"Unknown model for {session_state['app']}: {mid}"})
        return
    session_state["model"] = mid
    _rebuild_adapter_for(ws)
    await manager.broadcast({"type":"model_changed","model":mid})
    return
```
8. In `session.py` `Session.__init__`: add `app: str = "piagent"`, `model: str = ""`; set `self.app`, `self.model`; in `to_dict` add `"app": self.app, "model": self.model`; in `from_dict` read them with defaults.

- [ ] **Step 4: Run tests**

Run: `cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && PYTHONPATH=. python3 -m pytest phase4_chat_ui/test_app.py -v`
Expected: PASS (new test + existing tests still green)

- [ ] **Step 5: Commit**

```bash
git add phase4_chat_ui/app.py phase4_chat_ui/session.py phase4_chat_ui/test_app.py
git commit -m "feat(phase4): wire /api/apps + set_app/set_model WS handlers, per-session adapter"
```

---

### Task 5: UI — two topbar `<select>`s (app + model)

**Files:**
- Modify: `phase4_chat_ui/static/index.html`
- Modify: `phase4_chat_ui/static/style.css`
- Modify: `phase4_chat_ui/static/app.js`
- Test: manual (no automated UI test harness exists; verify via running server)

**Interfaces:**
- Consumes (from Task 4): initial WS payload keys `apps`, `active_app`, `active_model`; broadcast messages `app_changed` (with `apps`), `model_changed`.
- Produces: topbar selects `#app-select` and `#model-select`; JS keeps them in sync with server.

- [ ] **Step 1: Add the two selects to the topbar (index.html)**

After the existing `<button id="state-refresh">` in the `<header class="topbar">`, add:
```html
<select id="app-select" class="topbar-select" title="Agentic app"></select>
<select id="model-select" class="topbar-select" title="Model"></select>
```

- [ ] **Step 2: Add styling (style.css)** — append:
```css
.topbar-select {
  border: 1px solid var(--sky);
  border-radius: 8px;
  padding: 4px 8px;
  font: inherit;
  background: var(--glass-strong);
  color: var(--ink);
  max-width: 180px;
}
.topbar-select:disabled { opacity: 0.5; }
```

- [ ] **Step 3: Wire JS (app.js)**
  - Add element refs near the other `getElementById` calls:
    ```javascript
    const appSelect = document.getElementById("app-select");
    const modelSelect = document.getElementById("model-select");
    ```
  - Add a `renderApps(apps, activeApp, activeModel)` function:
    ```javascript
    function renderApps(apps, activeApp, activeModel) {
      appSelect.innerHTML = "";
      apps.forEach(a => {
        const o = el("option", "", a.name);
        o.value = a.id;
        if (!a.available) o.disabled = true;
        if (a.id === activeApp) o.selected = true;
        appSelect.appendChild(o);
      });
      renderModels(apps, activeApp, activeModel);
    }
    function renderModels(apps, activeApp, activeModel) {
      const app = apps.find(a => a.id === activeApp) || { models: [] };
      modelSelect.innerHTML = "";
      app.models.forEach(m => {
        const o = el("option", "", m.name);
        o.value = m.id;
        if (m.id === activeModel) o.selected = true;
        modelSelect.appendChild(o);
      });
    }
    ```
  - In the WS message handler, handle the new payloads:
    ```javascript
    case "apps":
      renderApps(msg.apps, msg.active_app, msg.active_model);
      break;
    case "app_changed":
      renderApps(msg.apps, msg.app, /*keep model*/ modelSelect.value);
      break;
    case "model_changed":
      modelSelect.value = msg.model;
      break;
    ```
    Also populate from the initial connect payload: in the block that reads the first `project`/handshake message, also call `renderApps(msg.apps, msg.active_app, msg.active_model)` when those keys exist.
  - Add change listeners:
    ```javascript
    appSelect.onchange = () => send({ type: "set_app", app: appSelect.value });
    modelSelect.onchange = () => send({ type: "set_model", model: modelSelect.value });
    ```

- [ ] **Step 4: Manual verification**
  Start the server (`setsid bash /tmp/pyagent_run.sh >/tmp/pyagent_server.log 2>&1 </dev/null & disown`), open `http://127.0.0.1:8123`:
  - Topbar shows "PiAgent" + a model dropdown listing the 15 `opencode-go` models, with `minimax-m3` selected.
  - OpenCode select is enabled; selecting it repopulates the model dropdown with `provider/model` ids (different list).
  - Anti-gravity select is disabled/greyed.
  - Switching app then model sends WS messages; chat routes to the chosen app.
  - Reload page → selection persists (per session).

- [ ] **Step 5: Commit**

```bash
git add phase4_chat_ui/static/index.html phase4_chat_ui/static/style.css phase4_chat_ui/static/app.js
git commit -m "feat(phase4): topbar app switcher + per-app model picker UI"
```

---

### Task 6: Persistence in `Session` + `switch_session` rebuild

**Files:**
- Modify: `phase4_chat_ui/session.py` (done fields in Task 4; add save on set)
- Modify: `phase4_chat_ui/app.py` (`switch_session` rebuild; persist app/model when set)
- Test: `phase4_chat_ui/test_session.py`, `phase4_chat_ui/test_app.py`

**Interfaces:**
- Consumes: `Session.app`/`Session.model` (Task 4), `_rebuild_adapter_for` (Task 4).
- Produces: when `set_app`/`set_model` succeed, also update the active session object's `app`/`model` and `save()`; `switch_session` rebuilds the per-socket adapter from the loaded session's `app`/`model` and includes `active_app`/`active_model` in broadcasts.

- [ ] **Step 1: Write the failing test**

```python
# test_session.py
def test_session_persists_app_and_model(tmp_path):
    from phase4_chat_ui.session import Session
    s = Session(session_id="sx", name="n", project="/x/y.kdenlive")
    s.app = "opencode"
    s.model = "opencode-go/minimax-m3"
    s.save()
    loaded = Session.load("sx")
    assert loaded.app == "opencode"
    assert loaded.model == "opencode-go/minimax-m3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && PYTHONPATH=. python3 -m pytest phase4_chat_ui/test_session.py::test_session_persists_app_and_model -v`
Expected: FAIL — `AttributeError: 'Session' object has no attribute 'app'` (if Task 4 only added to_dict without attribute) or assertion error.

- [ ] **Step 3: Implement**
  - In `Session.__init__` (session.py) ensure `self.app`/`self.model` attributes exist (Task 4 may have only set in to_dict). Set `self.app = app; self.model = model`.
  - In `app.py` `set_app`/`set_model` success paths, after rebuilding adapter, also do:
    ```python
    sess = sessions_cache.get(ws_session_map.get(ws))
    if sess:
        sess.app = target; sess.model = mid
        sess.save()
    ```
  - In `switch_session`, after `ws_session_map[ws] = target_id`, call `_rebuild_adapter_for(ws)` (which now uses `session_state["app"]` — so also set `session_state["app"] = loaded.app; session_state["model"] = loaded.model` before rebuild, so the per-socket adapter matches the session). Include `active_app`/`active_model` in the `session_list` broadcast.

- [ ] **Step 4: Run tests**

Run: `cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && PYTHONPATH=. python3 -m pytest phase4_chat_ui/test_session.py phase4_chat_ui/test_app.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add phase4_chat_ui/session.py phase4_chat_ui/app.py phase4_chat_ui/test_session.py phase4_chat_ui/test_app.py
git commit -m "feat(phase4): persist app/model per session + rebuild adapter on switch"
```

---

### Task 7: Full test suite + manual E2E

**Files:**
- Run: `phase4_chat_ui/test_app.py`, `phase4_chat_ui/test_session.py`, `phase4_chat_ui/test_agent_adapters.py`, plus existing `test_app.py` thinking/stop/image/reload tests.

**Interfaces:** none new; integration verification.

- [ ] **Step 1: Run the whole chat-UI suite**

Run: `cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && PYTHONPATH=. python3 -m pytest phase4_chat_ui/ -v`
Expected: ALL PASS (no regressions to thinking relay, stop, image paste, reload banner, sessions).

- [ ] **Step 2: Manual E2E via running server**
  Using a fresh server launch, in a browser at `http://127.0.0.1:8123`:
  1. Confirm `GET /api/apps` returns piagent (available, 15 models), opencode (available, provider/model list), antigravity (unavailable, []).
  2. Send a prompt on PiAgent (default) → works as before.
  3. Switch app dropdown to OpenCode → model dropdown repopulates with different ids → send a prompt → routes to `opencode run`.
  4. Switch model within OpenCode → chat uses new model.
  5. Reload page → app/model selection restored from session.
  6. Anti-gravity option is disabled and not selectable.

- [ ] **Step 3: Commit (if any test fixes needed)**
  Only commit if a test was added/fixed during this task; otherwise skip commit and report green.

```bash
git add -A && git commit -m "test(phase4): full suite green for multi-app switcher + per-app model picker"
```
(Only if changes exist.)
