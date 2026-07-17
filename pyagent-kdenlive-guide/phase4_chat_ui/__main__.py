"""`python3 -m phase4_chat_ui` launches the FastAPI server via uvicorn."""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="phase4_chat_ui",
        description="Launch the pyagent chat UI server.",
    )
    parser.add_argument("--project", required=True,
                        help="Path to the .kdenlive file to edit.")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Bind host (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8765,
                        help="Bind port (default: 8765).")
    parser.add_argument("--provider", default="opencode",
                        help="pi provider name (default: opencode).")
    parser.add_argument("--model", default="minimax-m3",
                        help="pi model id (default: minimax-m3).")
    parser.add_argument("--pi-binary", default=None,
                        help="Override the `pi` binary path (default: shutil.which('pi')).")
    parsed = parser.parse_args(argv)

    import uvicorn
    from phase4_chat_ui.app import create_app

    app = create_app(
        project=parsed.project,
        provider=parsed.provider,
        model=parsed.model,
        pi_binary=parsed.pi_binary,
    )
    uvicorn.run(app, host=parsed.host, port=parsed.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
