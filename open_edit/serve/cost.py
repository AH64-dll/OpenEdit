"""Cost computation for the Open Edit server (v1.4 P1-3).

Three responsibilities:

1. **Pricing config** — load ``serve/pricing.json`` and look up a
   per-model rate card. Used by the anthropic / openai providers,
   which return a SDK ``usage`` object that we multiply against
   the rate card to compute USD cost. The ``pi`` provider does NOT
   use this file — pi already computes its own cost and we reuse
   that. Pricing values will go stale; see the staleness comment in
   ``pricing.json``.

2. **Anthropic / OpenAI cost math** — pure functions that take a
   usage dict and a model name, and return ``(turn_tokens,
   turn_cost_usd)`` or ``None`` (if the model is unknown — the
   agent loop maps ``None`` to ``source: "unavailable"``).

3. **Pi session JSONL parser** — given a session file
   (``~/.pi/agent/sessions/<encoded-cwd>/<timestamp>_<sid>.jsonl``),
   sum the ``usage.cost.total`` and ``usage.totalTokens`` across all
   assistant-message entries. Two variants:

   - ``parse_pi_session_usage(path)`` — full-file aggregate.
   - ``parse_pi_session_usage_delta(path, last_size)`` — only the
     bytes appended after ``last_size``. If the file shrank (pi
     truncated the session), the delta resets to 0 and the full
     file is reported; the caller updates its baseline to
     ``new_file_size`` so subsequent deltas don't double-count.

   Plus ``find_pi_session_file(sid, sessions_dir)`` — locate the
   session file by id, tolerating the timestamp prefix.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# The pricing file lives next to this module. The relative path is
# stable; resolving it via __file__ means tests that monkeypatch the
# module attribute can redirect the lookup.
_PRICING_PATH_DEFAULT = str(Path(__file__).resolve().parent / "pricing.json")
PRICING_PATH = _PRICING_PATH_DEFAULT  # patched by tests


# ---------------------------------------------------------------------------
# Pricing config
# ---------------------------------------------------------------------------

def load_pricing() -> dict[str, dict[str, Any]]:
    """Load the pricing config from ``PRICING_PATH``.

    Returns a nested dict: ``{provider: {model: {rate_name: value}}}``.
    Raises ``FileNotFoundError`` if the file is missing — we do NOT
    silently return $0 cost, because that would mislead users.
    """
    with open(PRICING_PATH, encoding="utf-8") as fh:
        raw = json.load(fh)
    # Strip the leading ``_comment`` key (if present) so callers can
    # iterate providers cleanly.
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def lookup_pricing(provider: str, model: str) -> dict[str, float] | None:
    """Look up the rate card for a provider/model.

    Returns ``None`` if either the provider or the model is unknown.
    The agent loop maps ``None`` to ``source: "unavailable"``.
    """
    try:
        return load_pricing()[provider][model]
    except KeyError:
        return None


# ---------------------------------------------------------------------------
# Anthropic cost computation
# ---------------------------------------------------------------------------

def compute_anthropic_cost(
    usage: dict[str, Any], model: str,
) -> tuple[int, float] | None:
    """Compute (turn_tokens, turn_cost_usd) for one Anthropic call.

    ``usage`` is the ``final.usage`` object from the Anthropic SDK
    streaming response (or a plain dict with the same fields).
    Recognized keys: ``input_tokens``, ``output_tokens``,
    ``cache_creation_input_tokens`` (cache writes), and
    ``cache_read_input_tokens``. Missing keys default to 0.

    Returns ``None`` if the model is unknown (callers should map to
    ``source: "unavailable"``).
    """
    rates = lookup_pricing("anthropic", model)
    if rates is None:
        return None
    inp = int(usage.get("input_tokens", 0) or 0)
    out = int(usage.get("output_tokens", 0) or 0)
    cache_write = int(usage.get("cache_creation_input_tokens", 0) or 0)
    cache_read = int(usage.get("cache_read_input_tokens", 0) or 0)
    # Tokens reported for a turn = input + output + cache tokens.
    # Cache tokens are tokens too, so they belong in the token count.
    tokens = inp + out + cache_write + cache_read

    cost = (
        inp * float(rates.get("input_per_1m", 0))
        + out * float(rates.get("output_per_1m", 0))
        + cache_write * float(rates.get("cache_write_per_1m", 0))
        + cache_read * float(rates.get("cache_read_per_1m", 0))
    ) / 1_000_000.0
    return tokens, cost


# ---------------------------------------------------------------------------
# OpenAI cost computation
# ---------------------------------------------------------------------------

def compute_openai_cost(
    usage: dict[str, Any], model: str,
) -> tuple[int, float] | None:
    """Compute (turn_tokens, turn_cost_usd) for one OpenAI call.

    ``usage`` is the ``chunk.usage`` object (final chunk only — the
    OpenAI streaming response carries usage on the last chunk). The
    wire shape is ``prompt_tokens`` / ``completion_tokens``, with an
    optional ``prompt_tokens_details.cached_tokens`` (informational;
    we don't discount because the shipped pricing for gpt-4o/gpt-4o-mini
    doesn't expose a separate cache rate).
    """
    rates = lookup_pricing("openai", model)
    if rates is None:
        return None
    inp = int(usage.get("prompt_tokens", 0) or 0)
    out = int(usage.get("completion_tokens", 0) or 0)
    tokens = inp + out

    cost = (
        inp * float(rates.get("input_per_1m", 0))
        + out * float(rates.get("output_per_1m", 0))
    ) / 1_000_000.0
    return tokens, cost


# ---------------------------------------------------------------------------
# Pi session JSONL
# ---------------------------------------------------------------------------

def find_pi_session_file(session_id: str, sessions_dir: Path) -> Path | None:
    """Find the session file whose name ends with ``_<session_id>.jsonl``.

    Pi names files ``<timestamp>_<session_id>.jsonl`` (e.g.
    ``2026-07-20T11-30-44-319Z_cc69ce05-602a-4e64-80f6-c7a429b23238.jsonl``).
    We match on the suffix, not the timestamp, so we don't have to
    parse the date out of the prefix.

    The session file lives one level deep under ``sessions_dir``
    (in the encoded-CWD subdirectory), but we walk recursively so
    we don't depend on the exact subdir name — the encoded CWD can
    change between test runs.

    Returns ``None`` if the directory doesn't exist or no matching
    file is present.
    """
    if not sessions_dir.exists():
        return None
    suffix = f"_{session_id}.jsonl"
    for entry in _iter_files(sessions_dir):
        if entry.name.endswith(suffix):
            return entry
    return None


def _iter_files(root: Path):
    """Yield every regular file under ``root`` recursively. Skips
    symlinks to avoid following weird filesystem layouts."""
    for entry in root.iterdir():
        if entry.is_file():
            yield entry
        elif entry.is_dir():
            yield from _iter_files(entry)


def _accumulate_session_usage(path: Path) -> dict[str, Any]:
    """Walk every line of the session file, summing assistant-message usage.

    Returns ``{tokens, cost_usd}``. The file is read line-by-line
    (jsonl) so we never have to load the whole thing into memory;
    pi session files can grow large for long conversations.
    """
    total_tokens = 0
    total_cost = 0.0
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                # Skip malformed lines (a half-written line, a stray
                # non-JSON entry). The next parse from a fresh
                # position will pick up the recovery; better than
                # crashing the whole agent turn.
                continue
            if obj.get("type") != "message":
                continue
            msg = obj.get("message") or {}
            if msg.get("role") != "assistant":
                continue
            usage = msg.get("usage")
            if not isinstance(usage, dict):
                continue
            total_tokens += int(usage.get("totalTokens", 0) or 0)
            cost = usage.get("cost")
            if isinstance(cost, dict):
                total_cost += float(cost.get("total", 0) or 0)
    return {"tokens": total_tokens, "cost_usd": total_cost}


def parse_pi_session_usage(path: Path) -> dict[str, Any]:
    """Parse the entire pi session file and return aggregate usage.

    Returns ``{tokens: int, cost_usd: float, file_size: int}``. If
    the file doesn't exist, returns zeros — the agent loop decides
    whether to surface that as ``source: "unavailable"``.
    """
    if not path.exists():
        return {"tokens": 0, "cost_usd": 0.0, "file_size": 0}
    out = _accumulate_session_usage(path)
    out["file_size"] = path.stat().st_size
    return out


def parse_pi_session_usage_delta(
    path: Path, last_size: int,
) -> dict[str, Any]:
    """Parse only the bytes appended after ``last_size``.

    The agent loop calls this after each pi turn: it knew the file
    was N bytes long before pi ran, and now wants only the new
    bytes (the cost incurred during this turn). If the file shrank
    (pi truncated or rotated the session), we treat the entire
    file as fresh and the caller resets its baseline — we never
    report a negative cost.

    Returns ``{tokens, cost_usd, new_file_size, reset}`` where
    ``reset`` is True iff the file was shorter than ``last_size``
    (truncation detected). The caller uses ``reset`` to decide
    whether to overwrite its stored session-cost baseline.
    """
    if not path.exists():
        return {
            "tokens": 0, "cost_usd": 0.0,
            "new_file_size": 0, "reset": last_size > 0,
        }
    current_size = path.stat().st_size
    if current_size < last_size:
        # Truncation / rotation: read the whole file and tell the
        # caller its baseline was reset.
        out = _accumulate_session_usage(path)
        out["new_file_size"] = current_size
        out["reset"] = True
        return out

    if current_size == last_size:
        # No new content — caller sees zero cost, no reset.
        return {
            "tokens": 0, "cost_usd": 0.0,
            "new_file_size": current_size, "reset": False,
        }

    with path.open("rb") as fh:
        fh.seek(last_size)
        new_bytes = fh.read()
    new_text = new_bytes.decode("utf-8", errors="replace")

    total_tokens = 0
    total_cost = 0.0
    for line in new_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") != "message":
            continue
        msg = obj.get("message") or {}
        if msg.get("role") != "assistant":
            continue
        usage = msg.get("usage")
        if not isinstance(usage, dict):
            continue
        total_tokens += int(usage.get("totalTokens", 0) or 0)
        cost = usage.get("cost")
        if isinstance(cost, dict):
            total_cost += float(cost.get("total", 0) or 0)

    return {
        "tokens": total_tokens,
        "cost_usd": total_cost,
        "new_file_size": current_size,
        "reset": False,
    }


# ---------------------------------------------------------------------------
# Pi session directory resolution
# ---------------------------------------------------------------------------

def default_pi_sessions_dir() -> Path:
    """Return the directory where ``pi`` stores session JSONLs for
    the *server's* current working directory.

    Pi encodes the CWD by replacing ``/`` with ``-`` and bookending
    with ``-`` (so ``/home/ah64/apps/mlt-pipeline`` becomes
    ``--home-ah64-apps-mlt-pipeline--``). The base path is
    ``~/.pi/agent/sessions/`` — overridable via
    ``OPEN_EDIT_PI_SESSIONS_DIR`` for tests and unusual installs.
    """
    override = os.environ.get("OPEN_EDIT_PI_SESSIONS_DIR", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".pi" / "agent" / "sessions"


def encoded_cwd_segment(cwd: Path) -> str:
    """Return pi's CWD encoding for a given path. Exposed for tests."""
    return "-" + str(cwd).replace("/", "-") + "-"
