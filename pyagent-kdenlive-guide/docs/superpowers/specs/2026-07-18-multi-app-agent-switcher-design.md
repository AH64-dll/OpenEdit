# Design: Multi-App Agent Switcher (Model Picker)

**Date:** 2026-07-18
**Status:** Approved (user sign-off via chat)
**Scope:** Browser chat UI gains a topbar **app switcher + model picker** so the user can change, at runtime, which agentic app the chat talks to (PiAgent / OpenCode) and which model that app uses. Anti-gravity is scaffolded but disabled.

---

## 1. Goal & Concept

Today the model is fixed at server startup (`--model minimax-m3`) and only PiAgent is wired. We want the browser to:

1. Show a dropdown of **agentic apps** (PiAgent, OpenCode, [Anti-gravity — disabled]).
2. Show a **model dropdown** that is populated **from the selected app's own model source** (not a shared hard-coded list). Switching apps repopulates the model list.
3. Route the chat to the chosen app + model **immediately, per session, persisted** across reload / session switch.

Key principle (user requirement): *the model list for OpenCode is NOT the same as for PiAgent, and must be fetched from each app's own origin.* PiAgent → `~/.pi/agent/models-store.json`; OpenCode → its own providers/config; (future) Anti-gravity → its API.

---

## 2. Architecture

```
browser (topbar)
  ├── app dropdown      (PiAgent ▾ / OpenCode ▾ / Anti-gravity [disabled])
  └── model dropdown   (repopulated from selected app's list)
        │  WS: set_app / set_model
        ▼
FastAPI server (phase4_chat_ui/app.py)
  - session_state: {app, model, project, ...}
  - GET /api/apps  → [{id, name, available, models:[{id,name}]}]
  - AgentAdapter factory: build_adapter(app, model, project, session_id)
        │
        ├── PiAgentAdapter   → wraps existing PiClient (pi CLI, JSON stream)
        ├── OpenCodeAdapter  → opencode run --format json --model ... (new)
        └── AntiGravityAdapter (stub, unavailable)
```

Each WebSocket holds its own adapter instance in `ws_client_map[ws]`, mirroring the existing `PiClient` pattern. Switching app/model **recreates** the adapter for that socket (cancelling any in-flight task first, reusing the existing stop logic).

---

## 3. AgentAdapter Abstraction

A small protocol/ABC in a new module `phase4_chat_ui/agent_adapters.py`:

```python
class AgentAdapter(Protocol):
    app_id: str
    async def run_prompt(self, text: str,
                        image_paths: list[str] | None = None
                        ) -> AsyncIterator[NormalizedEvent]: ...
    def list_models(self) -> list[dict]: ...      # [{id, name, reasoning?}]
    def stop(self) -> None: ...
    @property
    def session_id(self) -> str: ...
```

`PiEvent` is the **existing** event shape already produced by `PiClient` (`kind` ∈ {message_delta, thinking, message, tool, error, done}). OpenCodeAdapter must parse `opencode run --format json` output into the **same** shape so `relay_event` (app.py) is unchanged.

### Implementations

**PiAgentAdapter** — thin wrapper over the current `PiClient` (pi CLI, `--mode json`, extension loaded). `list_models()` reads `~/.pi/agent/models-store.json` → `opencode-go.models[]` → `[{id, name, reasoning}]`. Unchanged streaming behaviour.

**OpenCodeAdapter** — launches:
```
opencode run --format json --model <provider/model> --file <img>... "<text>"
```
Parses its JSON event stream into `NormalizedEvent` (message_delta / tool / done / error). `list_models()` shells `opencode providers list` (or parses its config) → model list. Model id format is `provider/model` (different namespace than PiAgent's bare ids — this is exactly why lists are per-app).

**AntiGravityAdapter** — stub. `available=False` always. `list_models()` returns `[]`. `run_prompt()` raises/returns an `error` event "integration pending". Left so the menu + factory already support a 3rd app without further refactoring later.

### Factory

```python
def build_adapter(app: str, model: str, project: str,
                  session_id: str, pi_args: list[str]) -> AgentAdapter:
    if app == "opencode":   return OpenCodeAdapter(model, project, session_id)
    if app == "antigravity": return AntiGravityAdapter(...)
    return PiAgentAdapter(model=model, project=project,
                          session_id=session_id, pi_args=pi_args)
```

`/api/apps` is built by asking **each** adapter for its `list_models()` + an `available` flag (binary on PATH / port reachable). This guarantees the model list always comes from the app's own source.

---

## 4. WebSocket Protocol (additions)

| Msg (client→server) | Payload | Effect |
|---|---|---|
| `set_app` | `{app:"opencode"\|"piagent"\|"antigravity"}` | validate available → recreate adapter for socket → broadcast `app_changed` |
| `set_model` | `{model:"<id>"}` | validate against **active app's** list → recreate adapter → broadcast `model_changed` |

| Msg (server→client) | Payload | Effect |
|---|---|---|
| `apps` (on connect + on change) | `{apps:[{id,name,available,models:[...]}], active_app, active_model}` | populate both dropdowns |
| `app_changed` | `{app}` | UI updates app dropdown + repopulates model dropdown |
| `model_changed` | `{model}` | UI updates model dropdown |

In-flight task is cancelled (`active_tasks.pop(ws).cancel()`) and the adapter's `stop()` called before swapping — reuses the existing `stop` handler.

Persisted per session in `Session` (new fields `app`, `model`) so switching sessions / reloading restores the choice. On `switch_session`, the adapter is rebuilt from the session's stored `app`/`model`.

---

## 5. UI (topbar)

In `index.html` topbar, add two controls next to the existing project path / refresh:
- `<select id="app-select">` — options built from `/api/apps`; disabled options for unavailable apps.
- `<select id="model-select">` — options from the **selected app's** `models`; shows active model.

In `app.js`:
- On `apps` / `app_changed` / `model_changed` messages → re-render both selects.
- On `app-select` change → `send({type:"set_app", app})`; on `model-select` change → `send({type:"set_model", model})`.
- Changing app resets the model dropdown to that app's list (the user's explicit requirement: OpenCode's models ≠ PiAgent's).

Styling reuses the existing Frutiger-Aero `ghost-btn` / select styles in `style.css`.

---

## 6. Error Handling

- Unknown app → `error` event, no swap.
- App binary missing → `available:false` in `/api/apps`, dropdown option disabled.
- Model id not in active app's list → `error` event, no swap.
- OpenCode JSON parse failure → `error` event, adapter not swapped.
- Adapter launch failure (e.g. opencode not installed) → `error` event, keep prior adapter.

---

## 7. Testing

New/extended in `phase4_chat_ui/test_app.py` and a new `test_agent_adapters.py`:
1. `PiAgentAdapter.list_models()` parses `models-store.json` (fixture) → 15 models.
2. `OpenCodeAdapter.list_models()` parses `opencode providers list` output (mocked) → model list; bare-id rejection.
3. `build_adapter` returns correct type per app; Anti-gravity stub has `available=False`.
4. `set_app` / `set_model` WS handlers swap `ws_client_map[ws]` and broadcast `app_changed`/`model_changed`.
5. Invalid app/model → no swap + `error` event.
6. OpenCode JSON stream → `NormalizedEvent` mapping (message_delta / tool / done).
7. `/api/apps` reflects availability (binary-on-PATH detection).

Existing session / thinking / stop / image / reload-banner tests must stay green.

---

## 8. Out of Scope

- Anti-gravity live integration (no CLI/API wired yet) — stub only.
- Provider switching beyond the single configured provider per app.
- Server-restart-free model changes for the *default* at launch (still set via `--model`, now also overridable per session).

---

## 9. Implementation Order (for the plan)

1. `agent_adapters.py`: `AgentAdapter` protocol, `PiAgentAdapter` (wrap PiClient), `OpenCodeAdapter` (opencode CLI + JSON parse), `AntiGravityAdapter` stub, `build_adapter`, `list_apps()`.
2. `app.py`: `session_state` gains `app`; `Session` gains `app`/`model`; WS `set_app`/`set_model` handlers; `/api/apps`; initial `apps` handshake; rebuild adapter on `switch_session`; recreate-adapter helper (cancel in-flight first).
3. `index.html` + `style.css`: two topbar selects.
4. `app.js`: render selects from `apps`/`app_changed`/`model_changed`; send `set_app`/`set_model`; repopulate model list on app change.
5. Tests (§7).
6. Manual E2E: launch server, switch PiAgent↔OpenCode in browser, confirm model lists differ and chat routes correctly.
