"""CLI entry point. Thin: parse args, call runtime.run_op."""
from __future__ import annotations

import argparse
import json
import sys

from .runtime import run_op, _to_jsonable


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="phase3_pyagent_core")
    parser.add_argument("op")
    parser.add_argument("--project", required=True)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--args-json", default="{}")
    parsed = parser.parse_args(argv)
    try:
        args = json.loads(parsed.args_json)
    except json.JSONDecodeError as e:
        sys.stdout.write(
            json.dumps({"ok": False, "fatal": True, "error": str(e)}) + "\n"
        )
        return 2
    code, resp = run_op(parsed.op, args, parsed.project, parsed.catalog)
    sys.stdout.write(json.dumps(resp, default=_to_jsonable) + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
