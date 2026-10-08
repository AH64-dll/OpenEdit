"""Pricing configuration and SDK usage accounting for the optional review chat."""
from __future__ import annotations

import json
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
