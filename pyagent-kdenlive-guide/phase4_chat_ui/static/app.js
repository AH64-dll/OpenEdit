/* PyAgent chat UI — vanilla JS, WebSocket client. */

const transcript = document.getElementById("transcript");
const planSlot = document.getElementById("plan-slot");
const composer = document.getElementById("composer");
const input = document.getElementById("prompt-input");
const sendBtn = document.getElementById("send-btn");
const stopBtn = document.getElementById("stop-btn");
const statePanel = document.getElementById("state-panel");
const projectPathEl = document.getElementById("project-path");
const stateRefreshBtn = document.getElementById("state-refresh");
const quickActionsEl = document.getElementById("quick-actions");
const imagePreviews = document.getElementById("image-previews");
const newSessionBtn = document.getElementById("new-session-btn");
const sessionsList = document.getElementById("sessions-list");

let ws = null;
let pendingPlanId = null;
let _streamingBody = null;  // the in-progress assistant bubble during a turn
let pendingImages = [];
let activeSessionId = null;
let _thinkingMsgRow = null;

function setRunningState(running) {
  if (running) {
    sendBtn.style.display = "none";
    stopBtn.style.display = "inline-block";
    input.disabled = true;
  } else {
    sendBtn.style.display = "inline-block";
    stopBtn.style.display = "none";
    input.disabled = false;
    input.focus();
    clearThinking();
  }
}

function showThinking(text) {
  clearThinking();
  const row = el("div", "msg msg-assistant thinking-msg");
  row.appendChild(el("div", "who", "PyAgent (thinking)"));
  const body = el("div", "body text-thinking", text || "Analyzing...");
  const spinner = el("span", "thinking-spinner", "...");
  row.appendChild(body);
  row.appendChild(spinner);
  transcript.appendChild(row);
  transcript.scrollTop = transcript.scrollHeight;
  _thinkingMsgRow = row;
}

function clearThinking() {
  if (_thinkingMsgRow) {
    _thinkingMsgRow.remove();
    _thinkingMsgRow = null;
  }
}

function appendAssistantDelta(text) {
  clearThinking();
  if (!_streamingBody) {
    const row = el("div", "msg msg-assistant");
    row.appendChild(el("div", "who", "PyAgent"));
    _streamingBody = el("div", "body", text);
    row.appendChild(_streamingBody);
    transcript.appendChild(row);
    transcript.scrollTop = transcript.scrollHeight;
  } else {
    _streamingBody.textContent = text;
    transcript.scrollTop = transcript.scrollHeight;
  }
}

function finishAssistantMessage() {
  _streamingBody = null;
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function addMessage(role, text, images) {
  const row = el("div", "msg msg-" + role);
  const who = el("div", "who", role === "user" ? "You" : "PyAgent");
  const body = el("div", "body", text);
  row.appendChild(who);
  row.appendChild(body);
  if (images && images.length > 0) {
    for (const imgData of images) {
      const img = el("img", "msg-image");
      img.src = imgData;
      row.appendChild(img);
    }
  }
  transcript.appendChild(row);
  transcript.scrollTop = transcript.scrollHeight;
  return body;
}

function addToolEvent(tool, args, result, error) {
  const row = el("div", "msg msg-tool");
  const summary = el("div", "who", "tool · " + tool);
  const body = el("div", "body");
  const pretty = error
    ? "✗ " + error
    : JSON.stringify(args) + (result !== null ? "\n→ " + JSON.stringify(result) : "");
  body.textContent = pretty;
  row.appendChild(summary);
  row.appendChild(body);
  transcript.appendChild(row);
  transcript.scrollTop = transcript.scrollHeight;
}

function renderPlan(plan) {
  pendingPlanId = plan.plan_id;
  planSlot.innerHTML = "";
  const card = el("div", "plan-card pending");
  card.appendChild(el("div", "plan-head", "PyAgent wants to make these edits"));
  card.appendChild(el("div", "plan-summary", plan.summary || "(no summary)"));
  if (plan.diff) {
    const pre = el("pre", "plan-diff", plan.diff);
    card.appendChild(pre);
  }
  const actions = el("div", "plan-actions");
  const approve = el("button", "btn approve", "Approve");
  const reject = el("button", "btn reject", "Reject");
  approve.onclick = () => {
    send({ type: "approve", plan_id: pendingPlanId });
    clearPlan("approved");
  };
  reject.onclick = () => {
    send({ type: "reject", plan_id: pendingPlanId });
    clearPlan("rejected");
  };
  actions.appendChild(approve);
  actions.appendChild(reject);
  card.appendChild(actions);
  planSlot.appendChild(card);
}

function clearPlan(decision) {
  if (!pendingPlanId) return;
  const card = planSlot.querySelector(".plan-card");
  if (card) {
    card.classList.remove("pending");
    card.classList.add(decision === "approved" ? "applied" : "rejected");
    const actions = card.querySelector(".plan-actions");
    if (actions) actions.remove();
  }
  pendingPlanId = null;
}

function renderState(state) {
  statePanel.innerHTML = "";
  if (!state) {
    const p = el("p", "muted", "No project loaded.");
    statePanel.appendChild(p);
    return;
  }
  const table = document.createElement("table");
  table.className = "kv";
  function push(k, v) {
    const tr = document.createElement("tr");
    const td1 = el("td", "", k);
    const td2 = el("td", "", String(v));
    tr.appendChild(td1);
    tr.appendChild(td2);
    table.appendChild(tr);
  }
  push("name", state.name || "—");
  push("fps", state.fps ?? "—");
  push("resolution", `${state.width ?? "?"}×${state.height ?? "?"}`);
  push("tracks", state.track_count ?? "—");
  push("duration", state.duration_sec != null ? state.duration_sec + "s" : "—");
  statePanel.appendChild(table);
}

function toggleReloadBanner(show) {
  const banner = document.getElementById("reload-banner");
  if (banner) banner.style.display = show ? "flex" : "none";
}

// D6: user confirmed they reloaded Kdenlive — tell the server to clear the flag.
document.getElementById("reload-done").onclick = () => send({ type: "refresh_state" });

function status(text) {
  let s = document.getElementById("status-line");
  if (!s) {
    s = el("div", "", "");
    s.id = "status-line";
    s.className = "status-line";
    transcript.parentNode.insertBefore(s, transcript.nextSibling);
  }
  s.textContent = text;
}

let _reconnectDelay = 1500;
const MAX_RECONNECT_DELAY = 30000;

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen = () => {
    status("connected");
    _reconnectDelay = 1500;
  };
  ws.onclose = () => {
    status("disconnected — retrying…");
    setTimeout(connect, _reconnectDelay);
    _reconnectDelay = Math.min(_reconnectDelay * 2, MAX_RECONNECT_DELAY);
  };
  ws.onmessage = (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    handle(msg);
  };
}

function send(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
}

function renderSessions(sessions, activeId) {
  sessionsList.innerHTML = "";
  activeSessionId = activeId;
  sessions.forEach((s) => {
    const item = el("div", "session-item" + (s.session_id === activeId ? " active" : ""));
    const name = el("div", "session-name", s.name || s.session_id);
    
    const meta = el("div", "session-meta");
    const projName = s.project ? s.project.split("/").pop() : "no project";
    const projSpan = el("span", "", projName);
    const dateStr = s.last_modified ? new Date(s.last_modified * 1000).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : "";
    const dateSpan = el("span", "", dateStr);
    
    meta.appendChild(projSpan);
    meta.appendChild(dateSpan);
    
    item.appendChild(name);
    item.appendChild(meta);
    
    item.onclick = () => {
      if (s.session_id !== activeSessionId) {
        send({ type: "switch_session", session_id: s.session_id });
      }
    };
    sessionsList.appendChild(item);
  });
}

function renderHistory(messages) {
  transcript.innerHTML = "";
  clearThinking();
  _streamingBody = null;
  
  messages.forEach((m) => {
    if (m.role === "tool") {
      const row = el("div", "msg msg-tool");
      row.appendChild(el("div", "who", "tool · " + (m.tool_name || "info")));
      row.appendChild(el("div", "body", m.content));
      transcript.appendChild(row);
    } else {
      addMessage(m.role, m.content, m.images);
    }
  });
  transcript.scrollTop = transcript.scrollHeight;
}

function handle(msg) {
  switch (msg.type) {
    case "project":
      projectPathEl.textContent = msg.path || "—";
      break;
    case "message_delta":
      appendAssistantDelta(msg.text);
      break;
    case "thinking":
      showThinking(msg.text);
      break;
    case "message":
      if (msg.role === "assistant") finishAssistantMessage();
      addMessage(msg.role, msg.text, msg.images);
      break;
    case "tool":
      clearThinking();
      addToolEvent(msg.tool, msg.args || {}, msg.result ?? null, msg.error ?? null);
      break;
    case "plan":
      renderPlan(msg);
      break;
    case "plan_resolved":
      clearPlan(msg.decision);
      break;
    case "state":
      renderState(msg);
      toggleReloadBanner(msg.reload_needed === true);
      break;
    case "state_full":
      renderState(msg.info);
      break;
    case "status":
      status(msg.text);
      if (msg.text === "ready" || msg.text === "stopped") {
        setRunningState(false);
      } else if (msg.text === "thinking" || msg.text === "working" || msg.text === "running") {
        setRunningState(true);
      }
      break;
    case "error":
      setRunningState(false);
      addMessage("assistant", "⚠ " + msg.text);
      break;
    case "session_list":
      renderSessions(msg.sessions, msg.active_session_id);
      break;
    case "history":
      renderHistory(msg.messages);
      break;
  }
}

composer.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text && pendingImages.length === 0) return;
  _streamingBody = null;  // reset any stale in-progress bubble
  addMessage("user", text, pendingImages);
  send({ type: "prompt", text, images: pendingImages });
  input.value = "";
  pendingImages = [];
  renderPreviews();
  setRunningState(true);
});

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    composer.requestSubmit();
  }
});

input.addEventListener("paste", (e) => {
  const items = (e.clipboardData || e.originalEvent.clipboardData).items;
  for (const item of items) {
    if (item.type.indexOf("image") !== -1) {
      const file = item.getAsFile();
      const reader = new FileReader();
      reader.onload = (event) => {
        const base64 = event.target.result;
        pendingImages.push(base64);
        renderPreviews();
      };
      reader.readAsDataURL(file);
    }
  }
});

function renderPreviews() {
  imagePreviews.innerHTML = "";
  pendingImages.forEach((imgSrc, index) => {
    const thumb = el("div", "preview-thumb");
    const img = el("img");
    img.src = imgSrc;
    const removeBtn = el("button", "remove-btn", "×");
    removeBtn.onclick = (e) => {
      e.preventDefault();
      pendingImages.splice(index, 1);
      renderPreviews();
    };
    thumb.appendChild(img);
    thumb.appendChild(removeBtn);
    imagePreviews.appendChild(thumb);
  });
}

stopBtn.onclick = () => {
  send({ type: "stop" });
};

newSessionBtn.onclick = () => {
  send({ type: "new_session" });
};

stateRefreshBtn.onclick = () => send({ type: "refresh_state" });

const QUICK_ACTIONS = [
  { label: "Add crossfade between clips", prompt: "Add a crossfade transition between the last two clips on the timeline." },
  { label: "Append test clip", prompt: "Import the test clip and append it to the end of the first track." },
  { label: "List effects", prompt: "List the available video effects from the catalog." },
  { label: "Show timeline", prompt: "Show me the current timeline summary." },
  { label: "Render proxy", prompt: "Render a 640x360 proxy of the current project to /tmp/pyagent_proxy.mp4 and report the file size, duration, and elapsed render time." },
  { label: "Render final", prompt: "Render the project at full quality to /tmp/pyagent_final.mp4 using the project's own profile. This is slow — confirm the user is okay with it before proceeding." },
  { label: "Check QC", prompt: "Run the cheap deterministic QC checks (black frames, silence, audio levels) on /tmp/pyagent_proxy.mp4 over the full timeline and report any flags. If anything is flagged, pull a thumbnail for the affected timestamp and include it in the report." },
  { label: "Get thumbnail", prompt: "Pick a representative timestamp around the middle of the timeline and extract a thumbnail to /tmp/pyagent_thumb.jpg so the user can see what the project looks like right now." },
];

for (const qa of QUICK_ACTIONS) {
  const b = el("button", "qa-btn", qa.label);
  b.onclick = () => {
    addMessage("user", qa.prompt);
    send({ type: "prompt", text: qa.prompt });
    setRunningState(true);
  };
  quickActionsEl.appendChild(b);
}

connect();
