/* PyAgent chat UI — vanilla JS, WebSocket client.
 *
 * Protocol (server -> client, JSON):
 *   {type:"project", path:str}
 *   {type:"message_delta", role:"assistant", text:str}  # live partial, update in place
 *   {type:"message", role:"user"|"assistant", text:str}
 *   {type:"tool", tool:str, args:obj, result:obj|null, error:str|null}
 *   {type:"plan", plan_id:str, summary:str, diff:str}   # pending approval
 *   {type:"plan_resolved", plan_id:str, decision:"approved"|"rejected"}
 *   {type:"state", ...project_info_dict}                 # get_project_info
 *   {type:"state_full", info:dict, summary:dict|null}    # info + timeline
 *   {type:"status", text:str}
 *   {type:"error", text:str}
 * Client -> server:
 *   {type:"prompt", text:str}
 *   {type:"approve", plan_id:str}
 *   {type:"reject", plan_id:str}
 *   {type:"refresh_state"}
 */

const transcript = document.getElementById("transcript");
const planSlot = document.getElementById("plan-slot");
const composer = document.getElementById("composer");
const input = document.getElementById("prompt-input");
const sendBtn = document.getElementById("send-btn");
const statePanel = document.getElementById("state-panel");
const projectPathEl = document.getElementById("project-path");
const stateRefreshBtn = document.getElementById("state-refresh");
const quickActionsEl = document.getElementById("quick-actions");

let ws = null;
let pendingPlanId = null;
let _streamingBody = null;  // the in-progress assistant bubble during a turn

function appendAssistantDelta(text) {
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

function addMessage(role, text) {
  const row = el("div", "msg msg-" + role);
  const who = el("div", "who", role === "user" ? "You" : "PyAgent");
  const body = el("div", "body", text);
  row.appendChild(who);
  row.appendChild(body);
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
  if (!state) {
    statePanel.innerHTML = '<p class="muted">No project loaded.</p>';
    return;
  }
  const rows = [];
  const push = (k, v) => rows.push(`<tr><td>${k}</td><td>${v}</td></tr>`);
  push("name", state.name || "—");
  push("fps", state.fps ?? "—");
  push("resolution", `${state.width ?? "?"}×${state.height ?? "?"}`);
  push("tracks", state.track_count ?? "—");
  push("duration", state.duration_sec != null ? state.duration_sec + "s" : "—");
  statePanel.innerHTML = `<table class="kv">${rows.join("")}</table>`;
}

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

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen = () => status("connected");
  ws.onclose = () => {
    status("disconnected — retrying…");
    setTimeout(connect, 1500);
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

function handle(msg) {
  switch (msg.type) {
    case "project":
      projectPathEl.textContent = msg.path || "—";
      break;
    case "message_delta":
      appendAssistantDelta(msg.text);
      break;
    case "message":
      if (msg.role === "assistant") finishAssistantMessage();
      addMessage(msg.role, msg.text);
      break;
    case "tool":
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
      break;
    case "state_full":
      renderState(msg.info);
      break;
    case "status":
      status(msg.text);
      break;
    case "error":
      addMessage("assistant", "⚠ " + msg.text);
      break;
  }
}

composer.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  _streamingBody = null;  // reset any stale in-progress bubble
  addMessage("user", text);
  send({ type: "prompt", text });
  input.value = "";
});

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    composer.requestSubmit();
  }
});

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
  };
  quickActionsEl.appendChild(b);
}

connect();
