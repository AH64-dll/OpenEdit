# Open Edit Frontend UI & WebSocket Integration Analysis

## 1. Executive Summary

This report presents a thorough analysis of the frontend UI components, WebSocket client integration, turn state management, interrupt (Stop) button workflow, connection status handling, and pytest test suite setup for Open Edit (`/home/ah64/apps/mlt-pipeline/open_edit`).

---

## 2. Web Frontend Structure & Component Mapping

### 2.1 Architecture & Tech Stack
- **Framework**: Standard HTML5, CSS3, and Vanilla JavaScript (ES Modules). No React, Vue, Svelte, or external bundlers (Vite/Webpack) are used.
- **Module Structure**: Native browser `<script type="module" src="/app.js"></script>` loading.
- **Location**: `/home/ah64/apps/mlt-pipeline/open_edit/open_edit/serve/static/`

```
open_edit/serve/static/
├── index.html       # Single Page Application HTML shell
├── app.js           # Main ES module entry point, bootstrapper & DOM event binder
├── style.css        # CSS variable theme tokens & component styles
└── js/
    ├── api.js       # REST API wrapper methods (GET/POST/PUT/DELETE)
    ├── assets.js    # Left-panel asset grid renderer & preview modal logic
    ├── chat.js      # Center-panel chat log, tool cards, & auxiliary status widgets
    ├── dom.js       # DOM selector helpers, element builder, toast & modal managers
    ├── state.js     # Shared reactive state object & API response normalizers
    └── ws.js        # WebSocket connection lifecycle, exponential backoff & event router
```

### 2.2 Topbar Layout & Input Row
- **Topbar (`<header class="topbar">`)**:
  - **Left**: `.logo` ("Open Edit"), `#project-select` dropdown, `#btn-new-project` (`+ New`), `#btn-refresh-project` (`⟳`).
  - **Center**: `#llm-provider-select` dropdown, `#llm-model-select` dropdown, `#llm-tools-warn` warning indicator.
  - **Right**: `#btn-cmd-k` (`⌘K` command palette), `#btn-toggle-theme` (`🌙/☀️`), `#btn-settings` (`⚙️ Settings`), mobile drawer toggles, `#conn-status` indicator dot.
  - *Observation*: Topbar currently lacks a dedicated Stop/Interrupt button.
- **Chat Input Row (`.chat-input-row`)**:
  - `#chat-input`: Auto-growing `<textarea>` for prompt input (Enter to send, Shift+Enter newline).
  - `#btn-send`: Primary send button with arrow SVG.
  - `#btn-stop`: Secondary interrupt button (`<button id="btn-stop" class="btn btn-secondary hidden" title="Interrupt request">Stop ⏹</button>`).

### 2.3 Toast Notification System
- **DOM Container**: `<div id="toast" class="toast hidden"></div>` located at line 297 of `index.html`.
- **CSS Tokens**: `.toast`, `.toast.error`, `.toast.success`, `.toast.warn` in `style.css`.
- **JS Implementation**: `showToast(message, kind = '')` in `static/js/dom.js`:
  ```javascript
  export function showToast(message, kind = '') {
    const t = $('#toast');
    if (!t) return;
    t.textContent = message;
    t.className = 'toast ' + kind;
    setTimeout(() => t.classList.add('hidden'), 3000);
  }
  ```

---

## 3. Agent Turn State Tracking

### 3.1 UI State Machines
1. **Chat Status Widget (`createChatStatus`)** (`static/js/chat.js`):
   - State values: `'idle'` | `'thinking'` | `'tool_running'`.
   - Transitions:
     - `send()` → `'thinking'` (displays "AI thinking…").
     - `text` WS event → `'thinking'` (if not currently running a tool).
     - `tool_start` WS event → `'tool_running'` (displays "Running <tool_name>…").
     - `tool_result` WS event → `'thinking'`.
     - `done` / `error` WS event → `'idle'` (hides widget).
2. **Verification Chip Widget (`createVerifyChip`)** (`static/js/chat.js`):
   - State values: `'idle'` | `'checking'` | `'verified'` | `'failed'` | `'skipped'` | `'capped'`.
   - Driven by `verification_started` and `verification_result` WS events.
3. **Cost Badge Widget (`createCostBadge`)** (`static/js/chat.js`):
   - Displays turn cost and cumulative session cost, driven by `cost_update` WS events.

### 3.2 Input & Action Button Controls (`setChatEnabled`)
In `static/app.js`:
```javascript
function setChatEnabled(enabled) {
  const input = $('#chat-input');
  const btnSend = $('#btn-send');
  const btnStop = $('#btn-stop');
  if (input) input.disabled = !enabled;
  if (btnSend) {
    btnSend.disabled = !enabled;
    btnSend.classList.toggle('hidden', !enabled);
  }
  if (btnStop) {
    btnStop.classList.toggle('hidden', enabled);
  }
  if (enabled && input) input.focus();
}
```
*Current Behavior Gap*: `setChatEnabled(false)` is NOT called inside `handleSend()` when a prompt is dispatched. Consequently, during active turns, `#chat-input` remains enabled and `#btn-stop` remains hidden (`hidden` class is retained).

---

## 4. Interactive Request Interrupt (Stop ⏹) Button Strategy

### 4.1 UI Component Additions
To ensure the Stop button is accessible in both the topbar and the prompt input row:
1. **Topbar Stop Button**: Add `<button id="btn-topbar-stop" class="btn btn-danger btn-xs hidden" title="Interrupt turn">Stop ⏹</button>` to `.topbar-right` in `index.html` (alongside `#conn-status`).
2. **Input Row Stop Button**: Keep and un-hide `#btn-stop` in `.chat-input-row`.
3. **Event Binding**: Bind click listeners on both `#btn-stop` and `#btn-topbar-stop` to `cancelTurn()`.

### 4.2 Turn Control State Rules
When a turn starts (`handleSend()`):
- Set `setChatEnabled(false)` (or dedicated `setTurnRunning(true)` helper):
  - Disable `#chat-input`.
  - Hide `#btn-send` (`btnSend.disabled = true; btnSend.classList.add('hidden')`).
  - Un-hide `#btn-stop` AND `#btn-topbar-stop` (`classList.remove('hidden')`).

When a turn finishes (`done` / `error` event, or user clicks Stop):
- Call `setChatEnabled(true)` (or `setTurnRunning(false)`):
  - Enable `#chat-input`.
  - Show `#btn-send` (`btnSend.disabled = false; btnSend.classList.remove('hidden')`).
  - Hide `#btn-stop` AND `#btn-topbar-stop` (`classList.add('hidden')`).

---

## 5. Stop Button Execution & WebSocket Protocol Flow

### 5.1 Client-Side Execution (`cancelTurn`)
Current `cancelTurn()` implementation in `static/app.js`:
```javascript
function cancelTurn() {
  if (state.ws) {
    try {
      state.ws.send(JSON.stringify({ type: 'cancel' }));
      state.ws.close();
    } catch {}
    state.ws = null;
  }
  markTurnDone();
  if (state.chatStatus) state.chatStatus.onEvent({ type: 'done', stop_reason: 'cancelled' });
  setChatEnabled(true);
  showToast('Turn interrupted by user', 'warn');
  setTimeout(() => connectWS(), 250);
}
```
**Required Client Enhancements**:
1. Send WebSocket frame `{"type": "cancel"}` immediately.
2. Mark any in-flight tool cards as interrupted/cancelled (`completeToolCard`).
3. Reset `chatStatus` and `verifyChip` state machines to `'idle'`.
4. Re-enable prompt input via `setChatEnabled(true)`.
5. Display visual warning toast via `showToast('Turn interrupted by user', 'warn')`.
6. Schedule clean WebSocket reconnection.

### 5.2 Server-Side WebSocket Handling (`open_edit/serve/app.py` & `agent.py`)
- Currently, `ws_chat()` in `app.py` iterates `async for event in agent_mod.run_agent_turn(...)`. During turn execution, `ws_chat()` is blocked on generator iteration and does not read incoming WS text frames concurrently.
- **Server Enhancement Requirement**:
  - `ws_chat()` should run an `asyncio.Task` to listen for incoming client frames (`websocket.receive_text()`) concurrently with agent turn streaming.
  - When `{"type": "cancel"}` is received, set a cancellation event/flag or cancel the `run_agent_turn` task.
  - Yield/send `{"type": "done", "stop_reason": "cancelled"}` back to the client.

---

## 6. Connection Drop Toasts & Reconnect Feedback

### 6.1 Current Connection State Handling
- `setWsState(s)` in `static/js/ws.js` manages class name on `#conn-status`:
  - `'connected'`: Green dot (`.conn-status.connected`).
  - `'connecting'`: Yellow dot (`.conn-status.connecting`).
  - `'disconnected'`: Red/gray dot (`.conn-status.disconnected`).
- Reconnection logic (`scheduleReconnect` in `static/js/ws.js`):
  - Uses exponential backoff capped at 10 seconds: `Math.min(1000 * Math.pow(1.5, attempts - 1), 10000)`.
  - Window event listeners in `app.js` trigger `connectWS()` on `online` and tab `focus`.

### 6.2 Recommended Connection Toast Enhancements
1. **Connection Loss Toast**: In `ws.onclose` (when `state.currentProjectId` is present and disconnect was not user-initiated), invoke `showToast('Connection lost. Reconnecting…', 'warn')`.
2. **Reconnection Success Toast**: In `ws.onopen`, if `state.reconnectAttempts > 0`, invoke `showToast('Reconnected to server', 'success')`.

---

## 7. Pytest Unit & Integration Test Architecture

### 7.1 Test Suite Organization
- **Location**: `/home/ah64/apps/mlt-pipeline/open_edit/tests/`
- **Key Test Files**:
  - `test_serve_ws.py`: FastAPI `TestClient.websocket_connect` integration tests for `/api/chat/{project_id}`.
  - `test_serve_agent.py`: Agent turn loop unit tests (`run_agent_turn`, system prompt generation, tool execution).
  - `test_serve_chat_status.py`: Node.js harness unit tests for `createChatStatus` state machine.
  - `test_serve_cost_badge.py`: Unit tests for `createCostBadge` widget.
  - `test_serve_verify_chip.py`: Unit tests for `createVerifyChip` widget.
  - `test_serve_send_reconnect.py`: Tests for `handleSend` reconnect kick during `CONNECTING` socket state.
  - `_node_harness.py`: Pytest utility that executes frontend JS modules inside Node.js scripts to validate `window.OpenEdit.__testHooks`.

### 7.2 Running Pytest Tests
- Command: `pytest tests/test_serve_*.py`
- Test dependencies: `pytest`, `pytest-asyncio`, `fastapi`, `httpx`, Node.js (for JS harness tests).
