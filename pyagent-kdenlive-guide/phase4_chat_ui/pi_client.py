"""PiClient — wraps the `pi` CLI (JSON mode) as an async event source.

Each user prompt spawns a short-lived `pi --mode json --print` subprocess that
reuses a persistent session (via --session-id) so multi-turn context survives.
The subprocess emits JSON lines; we parse them into PiEvent objects.

The `binary` argument is injectable so tests can run a fake `pi` with no model
access. In production it defaults to the `pi` on PATH.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass
class PiEvent:
    """A normalized event emitted while a prompt is being processed."""
    kind: str  # "message" | "tool" | "plan" | "error" | "done"
    role: str | None = None          # for message: "user" | "assistant"
    text: str | None = None          # for message / error
    tool: str | None = None          # for tool
    args: dict | None = None         # for tool
    result: Any | None = None        # for tool
    error: str | None = None         # for tool / error


class PiClient:
    """Runs pi prompts and yields normalized PiEvent stream."""

    def __init__(
        self,
        provider: str,
        model: str,
        project: str,
        binary: str | None = None,
        session_id: str = "pyagent-chat",
        pi_args: list[str] | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.project = project
        self.binary = binary or shutil.which("pi") or "pi"
        self.session_id = session_id
        self._pi_args = pi_args if pi_args is not None else []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_prompt(self, text: str) -> AsyncIterator[PiEvent]:
        """Run one prompt and yield normalized events until the run ends."""
        # Collect pi's environment; expose the project path the same way the
        # Phase 3 extension expects it (PYAGENT_PROJECT).
        env = dict(os.environ)
        env["PYAGENT_PROJECT"] = self.project
        env.setdefault("PYAGENT_AUTO_APPROVE", "true")

        cmd = [
            self.binary,
            "--provider", self.provider,
            "--model", self.model,
            "--mode", "json",
            "--no-extensions",   # we load the extension explicitly below
            "--session-id", self.session_id,
            "--print", text,
        ]
        # Load the pyagent extension by path so the tools are registered.
        cmd += self._pi_args

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,
        )

        assert proc.stdout is not None
        # Buffer for accumulating streamed assistant text across deltas.
        assistant_text = ""
        saw_tool = False
        saw_error = False

        async for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            events = self._normalize(obj, assistant_text)
            for ev in events:
                if ev.kind == "message" and ev.role == "assistant":
                    assistant_text = ev.text or assistant_text
                if ev.kind == "tool":
                    saw_tool = True
                if ev.kind == "error":
                    saw_error = True
                yield ev

        await proc.wait()
        if proc.returncode != 0 and not saw_error:
            err = ""
            if proc.stderr is not None:
                err = (await proc.stderr.read()).decode("utf-8", "replace").strip()
            yield PiEvent(kind="error", text=err or f"pi exited {proc.returncode}")

    async def stop(self) -> None:
        """No persistent process to stop (one-shot per prompt)."""
        return

    # ------------------------------------------------------------------
    # JSON-mode parsing
    # ------------------------------------------------------------------

    def _normalize(self, obj: dict, current_text: str) -> list[PiEvent]:
        t = obj.get("type")
        if t in ("message_start", "message_end", "message_update"):
            return self._parse_message(obj)
        if t == "turn_end":
            return self._parse_turn_end(obj)
        if t == "agent_end":
            return [PiEvent(kind="done")]
        if t == "error":
            return [PiEvent(kind="error", text=str(obj.get("error", "unknown error")))]
        return []

    def _parse_message(self, obj: dict) -> list[PiEvent]:
        # message_update carries the live partial; message_end carries the final.
        if obj.get("type") == "message_update":
            ev = obj.get("assistantMessageEvent") or {}
            etype = ev.get("type")
            if etype in ("text_delta", "text_end"):
                partial = obj.get("message", {})
                text = self._extract_text(partial)
                if text:
                    return [PiEvent(kind="message", role="assistant", text=text)]
            return []
        if obj.get("type") == "message_end":
            msg = obj.get("message", {})
            role = msg.get("role")
            if role == "assistant":
                text = self._extract_text(msg)
                if text:
                    return [PiEvent(kind="message", role="assistant", text=text)]
        return []

    def _parse_turn_end(self, obj: dict) -> list[PiEvent]:
        events: list[PiEvent] = []
        msg = obj.get("message", {})
        # Assistant text (final).
        text = self._extract_text(msg)
        if text:
            events.append(PiEvent(kind="message", role="assistant", text=text))
        # Tool results from this turn.
        for tr in obj.get("toolResults", []) or []:
            tool = tr.get("toolName") or tr.get("tool")
            args = tr.get("args") or {}
            result = tr.get("result") or tr.get("content")
            error = tr.get("error")
            events.append(PiEvent(
                kind="tool", tool=tool, args=args,
                result=result, error=error,
            ))
        return events

    @staticmethod
    def _extract_text(message: dict) -> str:
        """Pull plain text out of a pi message content array."""
        parts = message.get("content")
        if not isinstance(parts, list):
            return ""
        out: list[str] = []
        for p in parts:
            if isinstance(p, dict) and p.get("type") == "text":
                out.append(p.get("text", ""))
        return "".join(out)
