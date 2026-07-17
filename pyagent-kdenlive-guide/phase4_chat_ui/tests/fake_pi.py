#!/usr/bin/env python3
"""Fake `pi --mode json` binary for tests.

Usage (as invoked by PiClient):
  fake_pi --provider X --model Y --mode json --no-extensions \
          --session-id S --print "<prompt>" [--extension ext.ts]

It emits a JSON-mode event stream to stdout and exits 0, simulating a single
turn: an assistant text message, one tool call+result, and turn/agent end.
"""
import json
import sys

def emit(obj):
    print(json.dumps(obj), flush=True)

def main():
    args = sys.argv[1:]
    # The prompt is the value after "--print".
    prompt = ""
    if "--print" in args:
        prompt = args[args.index("--print") + 1]

    emit({"type": "session", "version": 3, "id": "fake"})
    emit({"type": "agent_start"})
    emit({"type": "turn_start"})
    emit({"type": "message_start", "message": {"role": "user",
         "content": [{"type": "text", "text": prompt}]}})
    emit({"type": "message_end", "message": {"role": "user",
         "content": [{"type": "text", "text": prompt}]}})

    # Assistant thinking + text.
    emit({"type": "message_start", "message": {"role": "assistant", "content": []}})
    emit({"type": "message_update", "assistantMessageEvent": {"type": "text_delta"},
          "message": {"role": "assistant", "content": [{"type": "text", "text": "Echo: "}]}})
    emit({"type": "message_update", "assistantMessageEvent": {"type": "text_end"},
          "message": {"role": "assistant", "content": [{"type": "text", "text": "Echo: " + prompt}]}})
    emit({"type": "message_end", "message": {"role": "assistant",
         "content": [{"type": "text", "text": "Echo: " + prompt}]}})

    # Tool call + result surfaced at turn_end.
    emit({"type": "turn_end", "message": {"role": "assistant",
         "content": [{"type": "text", "text": "Echo: " + prompt}]},
         "toolResults": [
             {"toolName": "pyagent_get_project_info", "args": {},
              "result": {"ok": True, "name": "demo"}}
         ]})
    emit({"type": "agent_end", "messages": [], "willRetry": False})

if __name__ == "__main__":
    main()
