"""Async streaming LLM client for the Open Edit server.

Three backends supported via ``OPEN_EDIT_LLM_PROVIDER``:

- ``anthropic`` (default) — direct Anthropic SDK streaming.
- ``openai``              — direct OpenAI SDK streaming.
- ``pi``                  — spawn the ``pi`` CLI as a subprocess and parse
                            its JSON output. The pi process loads our
                            ``open_edit/serve/pi_extension/extension.ts``
                            which registers the 11 Open Edit tools.

Environment
-----------
``OPEN_EDIT_LLM_API_KEY``    — required for anthropic/openai.
``OPEN_EDIT_LLM_MODEL``      — model name (default ``claude-sonnet-4-5`` for
                                anthropic, ``gpt-4o`` for openai, ``minimax-m3``
                                for pi).
``OPEN_EDIT_LLM_PROVIDER``   — ``anthropic`` | ``openai`` | ``pi`` (default
                                ``anthropic``).
``OPEN_EDIT_LLM_MAX_TOKENS`` — per-turn cap (default 4096). Anthropic only.
``OPEN_EDIT_PI_BINARY``      — path to the ``pi`` binary (default: from PATH).
``OPEN_EDIT_PI_EXTENSION``   — path to the open_edit pi extension .ts file
                                (default: ``<pkg>/serve/pi_extension/extension.ts``).
``OPEN_EDIT_PI_PROVIDER``    — provider name passed to pi (default ``opencode-go``).
``OPEN_EDIT_PI_SESSION_ID``  — pi session id (set per-WS connection).

Package layout
--------------
- ``events.py``      — ``StreamEvent`` TypedDict + ``_coerce_event``.
- ``keys.py``        — API key / model / provider / max-tokens resolution.
- ``dispatcher.py``  — ``stream_chat`` (retry loop) + CLI conversation
                       serialization.
- ``cli/``           — generic subprocess driver + pi cost wrapper.
- ``sdk_anthropic.py`` / ``sdk_openai.py`` — SDK streaming providers.
"""
from ..cli_adapter import _pi_binary, _pi_extension_path, _pi_normalize_event
from .cli import _stream_cli, _stream_pi
from .dispatcher import _message_plain_text, _serialize_cli_conversation, stream_chat
from .events import StreamEvent, _coerce_event
from .keys import _api_key, _max_tokens, _model, _provider, effective_provider
from .sdk_anthropic import _stream_anthropic
from .sdk_openai import _stream_openai

__all__ = [
    "stream_chat",
    "StreamEvent",
    "effective_provider",
    "_coerce_event",
    "_stream_anthropic",
    "_stream_openai",
    "_stream_pi",
    "_stream_cli",
    "_pi_binary",
    "_pi_extension_path",
    "_pi_normalize_event",
    "_serialize_cli_conversation",
    "_message_plain_text",
    "_api_key",
    "_model",
    "_provider",
    "_max_tokens",
]
