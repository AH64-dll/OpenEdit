"""Optional SDK and CLI chat providers for the review UI. Editing tools are exposed over MCP."""
from .cli import _stream_cli
from .dispatcher import _message_plain_text, _serialize_cli_conversation, stream_chat
from .events import StreamEvent, _coerce_event
from .keys import _api_key, _max_tokens, _model, _provider, effective_provider
from .sdk_anthropic import _stream_anthropic
from .sdk_openai import _stream_openai

__all__ = [
    "StreamEvent",
    "_api_key",
    "_coerce_event",
    "_max_tokens",
    "_message_plain_text",
    "_model",
    "_provider",
    "_serialize_cli_conversation",
    "_stream_anthropic",
    "_stream_cli",
    "_stream_openai",
    "effective_provider",
    "stream_chat",
]
