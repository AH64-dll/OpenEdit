"""Patch for ``open_edit/cli.py`` — add the ``serve`` subcommand.

This file is NOT meant to be dropped into the repo as-is. Instead, use it
as a reference for the code you need to add to your existing
``open_edit/cli.py``. The exact integration point depends on how your CLI
is structured (argparse / click / typer), but the snippet below shows the
minimal argparse version.

Drop-in steps:
1. Open your existing ``open_edit/cli.py``.
2. Find the subparser registration block (search for ``add_subparsers`` or
   ``add_parser``).
3. Add the new ``serve`` subparser registration shown below.
4. Add the ``_run_serve`` handler (or equivalent) to the dispatch table.

The actual command does::

    uvicorn open_edit.serve.app:app --reload --host 0.0.0.0 --port 8000

so users can run ``open_edit serve`` to start the chat-driven backend.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any


def add_serve_subparser(subparsers: Any) -> None:
    """Register the ``serve`` subcommand on an argparse subparsers object.

    Usage in your existing CLI::

        parser = argparse.ArgumentParser(prog="open_edit")
        subparsers = parser.add_subparsers(dest="cmd", required=True)
        # ... existing subparsers ...
        from open_edit.serve._cli_patch import add_serve_subparser
        add_serve_subparser(subparsers)
    """
    p = subparsers.add_parser(
        "serve",
        help="Start the chat-driven FastAPI backend (uvicorn).",
        description=(
            "Start the Open Edit HTTP + WebSocket server. The server "
            "exposes a REST API under /api/ and a chat WebSocket at "
            "/api/chat/{project_id}. The static frontend (if present) is "
            "served at /."
        ),
    )
    p.add_argument(
        "--host",
        default=os.environ.get("OPEN_EDIT_SERVE_HOST", "127.0.0.1"),
        help="Bind host (default 127.0.0.1, env OPEN_EDIT_SERVE_HOST)",
    )
    p.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("OPEN_EDIT_SERVE_PORT", "8000")),
        help="Bind port (default 8000, env OPEN_EDIT_SERVE_PORT)",
    )
    p.add_argument(
        "--token",
        default=os.environ.get("OPEN_EDIT_TOKEN"),
        help=(
            "Optional bearer token required for remote (non-localhost) "
            "requests (env OPEN_EDIT_TOKEN). If unset, no auth is required."
        ),
    )
    p.add_argument(
        "--reload",
        action="store_true",
        default=False,
        help="Enable uvicorn auto-reload (dev mode).",
    )
    p.add_argument(
        "--log-level",
        default="info",
        choices=["critical", "error", "warning", "info", "debug", "trace"],
        help="Uvicorn log level (default info).",
    )
    p.set_defaults(func=_run_serve)


def _run_serve(args: argparse.Namespace) -> int:
    """Entry point for ``open_edit serve``.

    Imports uvicorn lazily so users who never run ``serve`` don't pay the
    import cost.
    """
    try:
        import uvicorn
    except ImportError:
        print(
            "ERROR: uvicorn is not installed. Run "
            "`pip install 'uvicorn[standard]'` (or `poetry install --with serve`).",
            file=sys.stderr,
        )
        return 1

    # Propagate the token into the environment so the auth middleware
    # (which reads OPEN_EDIT_TOKEN at request time) picks it up. Optional:
    # if no token was supplied, auth stays off.
    if getattr(args, "token", None):
        os.environ["OPEN_EDIT_TOKEN"] = args.token

    uvicorn.run(
        "open_edit.serve.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )
    return 0


# ---------------------------------------------------------------------------
# Minimal standalone CLI (for reference / direct invocation)
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """A minimal CLI that ONLY wires up the ``serve`` subcommand.

    Useful for testing the wiring in isolation::

        python -m open_edit.serve._cli_patch serve --port 8000
    """
    parser = argparse.ArgumentParser(prog="open_edit")
    subparsers = parser.add_subparsers(dest="cmd", required=True)
    add_serve_subparser(subparsers)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
