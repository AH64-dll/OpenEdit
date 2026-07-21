/* ============================================================
   chat.js — center-panel chat log + tool cards + the
   chat-status / cost-badge / search-results auxiliary widgets.

   The chat log is event-driven: the WebSocket module calls
   these functions when WS events land (text deltas, tool
   starts / results, errors, render notifications). The chat
   also exposes ``sendChatMessage`` for the chat input and the
   "Add to project" button in the search-results panel.
   ============================================================ */

import { $, el, fmtDuration, showToast, truncate } from './dom.js';
import { state } from './state.js';

// ----------------------------------------------------------
// Chat log
// ----------------------------------------------------------
export function clearChatLog() {
  const log = $('#chat-log');
  if (!log) return;
  log.innerHTML = '';
  // If there are no projects, the user can't chat — show a hint with
  // the recovery command (v1.4 P0-1: "no projects found" must not be
  // an opaque empty state). Otherwise the generic placeholder.
  if (state.projects && state.projects.length === 0) {
    log.appendChild(el('div', { class: 'empty-state' }, [
      'No projects yet. Run ',
      el('code', {}, ['open_edit init <root>/<name>']),
      ' in a terminal, then click ⟳ to refresh.',
    ]));
  } else {
    log.appendChild(el('div', { class: 'empty-state' }, ['Select a project to start chatting.']));
  }
  state.pendingAssistantMsg = null;
  state.pendingToolCards.clear();
}

function ensureChatPlaceholderGone() {
  const log = $('#chat-log');
  if (!log) return;
  const ph = log.querySelector('.empty-state');
  if (ph) ph.remove();
}

export function appendUserMessage(text) {
  ensureChatPlaceholderGone();
  const msg = el('div', { class: 'msg msg-user' }, [text]);
  $('#chat-log').appendChild(msg);
  scrollChatToBottom();
}

export function startAssistantMessage() {
  ensureChatPlaceholderGone();
  const msg = el('div', { class: 'msg msg-bot' }, []);
  $('#chat-log').appendChild(msg);
  state.pendingAssistantMsg = msg;
  state.pendingToolCards.clear();
  return msg;
}

export function appendTextDelta(text) {
  if (!state.pendingAssistantMsg) startAssistantMessage();
  const msg = state.pendingAssistantMsg;
  // Append a text node; we accumulate in the existing node.
  // If the last child is a text node, append to it; otherwise create one.
  const last = msg.lastChild;
  if (last && last.nodeType === 3 /* Node.TEXT_NODE */) {
    last.textContent += text;
  } else {
    msg.appendChild(document.createTextNode(text));
  }
  scrollChatToBottom();
}

export function appendToolCard(toolUseId, name, input) {
  ensureChatPlaceholderGone();
  const inputStr = (() => {
    try { return JSON.stringify(input); } catch { return String(input); }
  })();

  const spinner = el('div', { class: 'spinner' });
  const body = el('div', { class: 'tool-body' }, [
    el('div', { class: 'tool-name' }, [name]),
    el('div', { class: 'tool-input' }, [inputStr]),
  ]);
  const result = el('div', { class: 'tool-result hidden' });

  // v1.4 P1-1: search_assets gets a dedicated placeholder region that
  // the result panel replaces. The text-based resultEl stays hidden
  // but kept in the DOM for compatibility with ``completeToolCard``.
  const searchPanel = name === 'search_assets'
    ? el('div', { class: 'search-results-placeholder' })
    : null;

  const card = el('div', { class: 'tool-card' }, [
    el('div', { class: 'gear' }, ['⚙']),
    body,
    searchPanel,
    spinner,
    result,
  ]);
  // Insert BEFORE the pending assistant text message if it exists,
  // so tool cards appear above the final text. If there's no pending
  // assistant message yet, just append.
  if (state.pendingAssistantMsg && state.pendingAssistantMsg.textContent.length === 0) {
    // Replace the empty pending message with the tool card.
    state.pendingAssistantMsg.replaceWith(card);
    state.pendingAssistantMsg = null;
  } else {
    $('#chat-log').appendChild(card);
  }
  state.pendingToolCards.set(
    toolUseId,
    { card, spinner, result, name, searchPanel },
  );
  scrollChatToBottom();
}

export function completeToolCard(toolUseId, result, isError = false) {
  const entry = state.pendingToolCards.get(toolUseId);
  if (!entry) {
    // No matching start event; emit a compact completed card.
    const card = el('div', { class: 'tool-card' }, [
      el('div', { class: 'gear' }, ['⚙']),
      el('div', { class: 'tool-body' }, [
        el('div', { class: 'tool-name' }, ['(result)']),
        el('div', { class: 'tool-result' + (isError ? ' failed' : '') }, [truncate(JSON.stringify(result), 200)]),
      ]),
    ]);
    $('#chat-log').appendChild(card);
    scrollChatToBottom();
    return;
  }
  const { card, spinner, result: resultEl, name, searchPanel } = entry;
  spinner.remove();
  // v1.4 P1-1: delegate to the dedicated results panel renderer for
  // search_assets. The result shape matches what the Python tool
  // returns (see pyagent_search_assets.search_assets).
  if (name === 'search_assets' && searchPanel) {
    const panel = appendSearchResults(result || {}, searchPanel);
    if (panel) {
      // Replace the placeholder with the real panel.
      searchPanel.replaceWith(panel);
    }
    scrollChatToBottom();
    return;
  }
  const text = (() => {
    try {
      const r = typeof result === 'string' ? JSON.parse(result) : result;
      if (r && r.error) return `✗ ${r.error}`;
      return `✓ ${truncate(JSON.stringify(r), 160)}`;
    } catch {
      return `✓ ${truncate(String(result), 160)}`;
    }
  })();
  resultEl.textContent = text;
  resultEl.className = 'tool-result' + (isError ? ' failed' : '');
  resultEl.classList.remove('hidden');
  scrollChatToBottom();
}

// ----------------------------------------------------------
// Search results panel (v1.4 P1-1)
//
// Renders one card per result with a thumbnail, title, license badge,
// attribution hint, and an "Add to project" button. When the tool
// returns an error (e.g. the API key is missing), renders a clear
// error state so the user can fix the env and retry.
//
// The wire shape is the same dict the Python tool returns, so we
// never re-fetch or re-shape the data — we render what the LLM saw.
// ----------------------------------------------------------
export function appendSearchResults(result, mountPoint) {
  const root = mountPoint
    ? mountPoint
    : (el('div', { class: 'search-results' }));
  if (!root.classList.contains('search-results')) {
    root.classList.add('search-results');
  }
  // Empty out any previous render (e.g. when re-rendering the same
  // panel after a follow-up search).
  while (root.firstChild) root.removeChild(root.firstChild);

  if (result && result.error) {
    // Error state: a clear message + the cause.
    const errBox = el('div', { class: 'search-results-error' }, [
      el('div', { class: 'search-results-error-head' }, ['⚠ Search failed']),
      el('div', { class: 'search-results-error-body' }, [result.error]),
    ]);
    root.appendChild(errBox);
    return root;
  }

  const results = (result && result.results) || [];
  if (results.length === 0) {
    root.appendChild(el('div', { class: 'search-results-empty' }, [
      'No results. Try a different query.',
    ]));
    return root;
  }

  // Header summarising the query (so the user sees what was searched).
  const query = result.query || '';
  const kind = result.kind || '';
  if (query || kind) {
    const headBits = [];
    if (query) headBits.push(`for "${query}"`);
    if (kind) headBits.push(`(${kind})`);
    root.appendChild(el('div', { class: 'search-results-head' }, [
      `${results.length} result${results.length === 1 ? '' : 's'} ${headBits.join(' ')}`,
    ]));
  }

  // Grid of result cards.
  const grid = el('div', { class: 'search-results-grid' });
  for (const r of results) {
    grid.appendChild(_renderSearchResultCard(r));
  }
  root.appendChild(grid);
  return root;
}

function _renderSearchResultCard(r) {
  // License badge color: red for attribution-required, yellow for
  // permissive-but-credit-appreciated, green for public-domain.
  const license = (r && r.license) || 'Unknown';
  const licenseClass = r && r.attribution_required
    ? 'license-badge attr-required'
    : (license.toLowerCase().includes('cc0') || license.toLowerCase().includes('pexels')
        ? 'license-badge permissive'
        : 'license-badge');

  // Thumbnail: an <img> that fails soft if the upstream CDN is down.
  const thumb = el('img', {
    class: 'result-thumb',
    src: r.thumbnail_url || '',
    alt: r.title || '',
    loading: 'lazy',
  });
  thumb.addEventListener('error', () => {
    thumb.classList.add('thumb-error');
    thumb.replaceWith(el('div', { class: 'result-thumb thumb-error' }, ['(no preview)']));
  });

  const titleText = r.title || r.id || '(untitled)';
  const metaBits = [];
  if (r.kind) metaBits.push(r.kind);
  if (r.duration_seconds != null) metaBits.push(fmtDuration(r.duration_seconds));

  const card = el('div', { class: 'result-card', 'data-result-id': r.id || '' }, [
    thumb,
    el('div', { class: 'result-body' }, [
      el('div', { class: 'result-title' }, [titleText]),
      metaBits.length ? el('div', { class: 'result-meta' }, [metaBits.join(' · ')]) : null,
      el('div', { class: licenseClass }, [license]),
      r.attribution
        ? el('div', { class: 'result-attribution' }, [r.attribution])
        : null,
      el('button', {
        class: 'btn btn-secondary btn-sm result-import-btn',
        type: 'button',
      }, ['+ Add to project']),
    ]),
  ]);
  // Wire the import button. The simplest reliable cross-LLM path is
  // to send a chat message asking the assistant to import this result;
  // the assistant's tool schema already knows the import_asset shape.
  const btn = card.querySelector('.result-import-btn');
  if (btn) {
    btn.addEventListener('click', () => {
      const id = r.id || '';
      const ok = sendChatMessage(
        `Please import the search result with id "${id}" into the project.`
      );
      if (ok) {
        btn.disabled = true;
        btn.textContent = 'Requested…';
      }
    });
  }
  return card;
}

export function appendRenderEvent(path, mode) {
  const card = el('div', { class: 'render-card' }, [
    el('div', { class: 'render-icon' }, ['✓']),
    el('div', {}, [
      el('div', {}, [`Rendered (${mode})`]),
      el('div', { class: 'render-path' }, [path || '(no path)']),
    ]),
  ]);
  $('#chat-log').appendChild(card);
  scrollChatToBottom();
}

export function appendErrorMessage(message) {
  const msg = el('div', { class: 'msg msg-error' }, [`⚠ ${message}`]);
  $('#chat-log').appendChild(msg);
  scrollChatToBottom();
}

export function markTurnDone() {
  // If the assistant message has no text content (only tool cards were
  // emitted), remove the empty bubble.
  if (state.pendingAssistantMsg && state.pendingAssistantMsg.textContent.trim() === '') {
    state.pendingAssistantMsg.remove();
  }
  state.pendingAssistantMsg = null;
  state.pendingToolCards.clear();
}

function scrollChatToBottom() {
  const log = $('#chat-log');
  if (!log) return;
  log.scrollTop = log.scrollHeight;
}

// ----------------------------------------------------------
// Chat status indicator (v1.4 P1-2)
// ----------------------------------------------------------
// A small state machine that surfaces "AI is running" / "Running
// <tool>…" feedback near the chat input. The state is driven by the
// same WS events the chat log already consumes (see ``handleWsEvent``).
// Exposed as ``createChatStatus`` so Node-sandbox tests can drive it
// without a real DOM (see ``tests/test_serve_chat_status.py``).
//
// States: ``idle`` | ``thinking`` | ``tool_running``. ``idle`` is the
// resting state (no in-flight turn). ``thinking`` is entered
// immediately on ``send()`` and on a ``text`` event. A ``tool_start``
// event transitions to ``tool_running`` (with the tool name carried in
// the label) and stays there until ``tool_result``, which goes back to
// ``thinking`` so the user sees the model is still alive. The
// ``error`` and ``done`` events are both terminal — per the brief,
// the indicator "clears within one frame of ``DONE`` or ``error``",
// and both events converge on ``idle``. The error message itself is
// surfaced through the chat log / toast (see ``handleWsEvent``) so the
// chat-status pill does not need to render an error state.
export function createChatStatus(element) {
  let currentState = 'idle';
  let currentToolName = null;
  const labelEl = element && element.querySelector
    ? element.querySelector('.chat-status-text')
    : null;

  function setState(next, payload) {
    currentState = next;
    currentToolName = (payload && payload.name) || null;
    if (!element) return;
    // Use setAttribute rather than ``element.dataset.state`` so the
    // same code path is exercised by the Node-sandbox test stubs
    // (which intercept setAttribute but don't proxy property writes
    // to the ``dataset`` object).
    element.setAttribute('data-state', next);
    if (next === 'idle') {
      element.classList.add('hidden');
    } else {
      element.classList.remove('hidden');
    }
    if (labelEl) labelEl.textContent = statusLabel(next, currentToolName);
  }

  // Set the initial state explicitly so the DOM attribute, the
  // ``hidden`` class, and the label are all in sync — and so test
  // stubs that start in an ``unset`` state see the same first write
  // a real browser would.
  setState('idle');

  return {
    send() {
      // User just clicked Send — show the indicator immediately, even
      // before the first WS event arrives. This is the "no visual
      // indication of what the AI is doing" gap the brief calls out.
      setState('thinking');
    },
    onEvent(ev) {
      if (!ev || typeof ev.type !== 'string') return;
      switch (ev.type) {
        case 'text':
          // First text delta confirms the model is responding. If a
          // tool is running we leave it alone (the tool label is more
          // useful); otherwise switch to thinking.
          if (currentState !== 'tool_running') setState('thinking');
          break;
        case 'tool_start':
          setState('tool_running', { name: ev.name });
          break;
        case 'tool_result':
          // Tool finished — the model will either emit more text or
          // ``done`` next. Either way we're back to "thinking" until
          // the turn ends.
          if (currentState === 'tool_running') setState('thinking');
          break;
        case 'error':
          // Per the brief, the indicator clears within one frame of
          // ``DONE`` or ``error``. The error message itself is shown
          // via the chat log / toast (see ``handleWsEvent``), so the
          // chat-status pill does not render an error state.
          setState('idle');
          break;
        case 'done':
          setState('idle');
          break;
        // ``ready`` and ``render`` don't change chat-status state.
      }
    },
    reset() { setState('idle'); },
    getState() { return { state: currentState, toolName: currentToolName }; },
  };
}

function statusLabel(s, toolName) {
  if (s === 'thinking') return 'AI thinking…';
  if (s === 'tool_running') return `Running ${toolName || 'tool'}…`;
  return '';
}

// ----------------------------------------------------------
// Cost badge (v1.4 P1-3)
// ----------------------------------------------------------
// A small monospace pill that displays the per-turn + cumulative
// session cost, or an honest "cost n/a" state when the LLM
// provider doesn't report a per-token bill (e.g. the ``pi`` path
// through opencode-go, which is subscription-billed).
//
// Driven by the ``cost_update`` WS event from the agent loop:
//   {type, turn_tokens, turn_cost_usd, session_cost_usd, source}
//
// The badge is intentionally focused: it only reacts to
// ``cost_update``. Other WS events (text, tool_start, done,
// error) are handled by the chat-status indicator above it. This
// separation of concerns is what the brief meant by "the cost
// badge should not duplicate the chat-status indicator's logic".
//
// Exposed as ``window.OpenEdit.__testHooks.createCostBadge`` so
// Node-sandbox tests can drive the badge without a real DOM
// (see ``tests/test_serve_cost_badge.py``).
export function createCostBadge(element) {
  const labelEl = element && element.querySelector
    ? element.querySelector('.cost-badge-text')
    : null;

  function setLabel(text) {
    if (labelEl) labelEl.textContent = text;
  }

  function setSource(source) {
    if (!element) return;
    // Use setAttribute (same pattern as createChatStatus) so the
    // Node-sandbox test stubs that intercept setAttribute still work.
    element.setAttribute('data-source', source);
  }

  function setVisible(visible) {
    if (!element) return;
    if (visible) element.classList.remove('hidden');
    else element.classList.add('hidden');
  }

  function formatUsd(n) {
    // 2-4 fraction digits depending on magnitude. Very small
    // numbers (typical for a single pi turn) get 4 digits so
    // they don't show as "$0.00" when the user actually did
    // spend something. Larger numbers get 2 digits for compactness.
    if (n === 0) return '$0.00';
    if (n < 0.01) return '$' + n.toFixed(4);
    return '$' + n.toFixed(2);
  }

  // Start hidden — the badge appears only when the first
  // ``cost_update`` arrives, so we never show a stale label.
  setVisible(false);
  setSource('unavailable');
  setLabel('');

  return {
    onEvent(ev) {
      if (!ev || ev.type !== 'cost_update') return;
      const source = (ev.source === 'pi' || ev.source === 'computed')
        ? ev.source : 'unavailable';
      setSource(source);
      setVisible(true);
      if (source === 'unavailable') {
        // The brief: "When source == unavailable, show something
        // honest like 'cost n/a (subscription)' instead of a
        // fake $0.00." The exact wording is a UX choice; this
        // is the suggested form. Tests pin that we say "n/a"
        // and don't show a $0.00 fake.
        setLabel('cost n/a (subscription)');
        return;
      }
      const turnCost = Number(ev.turn_cost_usd) || 0;
      const sessionCost = Number(ev.session_cost_usd) || 0;
      setLabel(`${formatUsd(turnCost)} this turn · ${formatUsd(sessionCost)} session`);
    },
    reset() {
      setVisible(false);
      setSource('unavailable');
      setLabel('');
    },
  };
}

// ----------------------------------------------------------
// Chat sender
// ----------------------------------------------------------
export function sendChatMessage(text) {
  if (!state.ws || state.ws.readyState !== 1 /* WebSocket.OPEN */) {
    // The toast text is the user-facing promise that the system is
    // trying to recover. The actual reconnect is owned by ws.js
    // (it fires on onclose / online / focus), so this function
    // just reports the failure — see the ``OpenEdit.*`` registration
    // in app.js if you need to kick a reconnect from this path.
    showToast('Not connected. Retrying…', 'error');
    return false;
  }
  // Generate a conversation id if we don't have one yet.
  if (!state.conversationId) {
    state.conversationId = (typeof crypto !== 'undefined' && crypto.randomUUID)
      ? crypto.randomUUID()
      : `conv-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    try { localStorage.setItem('open_edit.conversation_id', state.conversationId); } catch {}
  }
  // The Prompt-1 backend accepts {message, conv_id}. The Prompt-2 contract
  // uses {type: "user_message", message, conversation_id}. Send BOTH shapes.
  const payload = {
    type: 'user_message',
    message: text,
    conversation_id: state.conversationId,
    conv_id: state.conversationId,
  };
  try {
    state.ws.send(JSON.stringify(payload));
    return true;
  } catch (e) {
    showToast(`Send failed: ${e.message}`, 'error');
    return false;
  }
}
