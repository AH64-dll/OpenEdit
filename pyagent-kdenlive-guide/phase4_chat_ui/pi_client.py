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
from typing import Any, AsyncIterator

from phase4_chat_ui.types import PiEvent


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
        self._current_proc: asyncio.subprocess.Process | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_prompt(self, text: str, image_paths: list[str] | None = None) -> AsyncIterator[PiEvent]:
        """Run one prompt and yield normalized events until the run ends."""
        # Collect pi's environment; expose the project path the same way the
        # Phase 3 extension expects it (PYAGENT_PROJECT).
        env = dict(os.environ)
        # The server process may inherit a broken PATH (e.g. a display-manager
        # session sets PATH=/org/freedesktop/...), which breaks `pi`/node and
        # silently prevents the pyagent extension from loading (no timeline tools).
        # Force a known-good PATH for the child so the extension always loads.
        _clean_path = (
            "/home/ah64/.local/bin:"
            "/home/ah64/.npm-global/bin:"
            "/home/ah64/.opencode/bin:"
            "/usr/local/sbin:/usr/local/bin:/usr/bin:/bin"
        )
        if not env.get("PATH") or "DisplayManager" in env.get("PATH", ""):
            env["PATH"] = _clean_path
        env["PYAGENT_PROJECT"] = self.project
        # Enable the Phase 3 extension's live-sync path. Without this the
        # extension's liveSyncEnabled() is false, edits skip LiveSync.apply
        # entirely, and no reload/notify is ever triggered (timeline appears
        # unchanged in Kdenlive). The file backend + reload notify only run
        # when PYAGENT_LIVE is set.
        env["PYAGENT_LIVE"] = "1"
        env.setdefault("PYAGENT_AUTO_APPROVE", "false")

        cmd = [
            self.binary,
            "--provider", self.provider,
            "--model", self.model,
            "--mode", "json",
            "--no-extensions",   # we load the extension explicitly below
            "--session-id", self.session_id,
        ]
        if image_paths:
            for ip in image_paths:
                cmd.append(f"@{ip}")
        cmd += [
            "--print", text,
        ]
        # Load the pyagent extension by path so the tools are registered.
        cmd += self._pi_args

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        try:
            self._current_proc = proc
            assert proc.stdout is not None
            # Buffer for accumulating streamed assistant text across deltas.
            assistant_text = ""
            saw_tool = False
            saw_error = False

            try:
                async with asyncio.timeout(1900.0):
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
            except TimeoutError:
                saw_error = True
                yield PiEvent(kind="error", text="pi subprocess timed out after 1900.0s")

            await proc.wait()
            if proc.returncode != 0 and not saw_error:
                err = ""
                if proc.stderr is not None:
                    err = (await proc.stderr.read()).decode("utf-8", "replace").strip()
                yield PiEvent(kind="error", text=err or f"pi exited {proc.returncode}")
        finally:
            if proc.returncode is None:
                try:
                    proc.kill()
                except Exception:
                    pass
            self._current_proc = None

    def stop(self) -> None:
        """Kill the currently running pi subprocess."""
        proc = self._current_proc
        if proc and proc.returncode is None:
            try:
                proc.kill()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # JSON-mode parsing
    # ------------------------------------------------------------------

    def _normalize(self, obj: dict, current_text: str) -> list[PiEvent]:
        t = obj.get("type")
        if t == "thinking":
            return [PiEvent(kind="thinking", text=str(obj.get("thinking", "")))]
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
        # Live partial text comes through message_update / text_delta for a
        # streaming feel; we emit it as kind="message_delta" so the UI can
        # update the in-progress bubble in place instead of appending. The
        # final text is delivered exactly once via message_end as kind=
        # "message". We deliberately ignore the message_update "text_end"
        # event, because it carries the same full text as message_end and
        # would duplicate every assistant message in the UI.
        if obj.get("type") == "message_update":
            ev = obj.get("assistantMessageEvent") or {}
            if ev.get("type") == "text_delta":
                partial = obj.get("message", {})
                text = self._extract_text(partial)
                if text:
                    return [PiEvent(kind="message_delta", role="assistant", text=text)]
            return []
        if obj.get("type") == "message_end":
            msg = obj.get("message", {})
            role = msg.get("role")
            if role == "assistant":
                text = self._extract_text(msg)
                if text:
                    return [PiEvent(kind="message", role="assistant", text=text,
                                cost=self._extract_cost(msg))]
        return []

    @staticmethod
    def _extract_cost(message: dict) -> float | None:
        """Pull USD cost from a pi message's usage.cost.total, if present."""
        usage = message.get("usage") if isinstance(message, dict) else None
        if not isinstance(usage, dict):
            return None
        cost = (usage.get("cost") or {}).get("total")
        if isinstance(cost, (int, float)) and cost > 0:
            return float(cost)
        return None


    def _parse_turn_end(self, obj: dict) -> list[PiEvent]:
        events: list[PiEvent] = []
        # NOTE: the assistant's final text is already delivered via
        # message_update (text_end) / message_end for this turn. Re-emitting
        # it here duplicates every assistant message in the UI, so we
        # only surface the tool results from the turn_end event.
        # Assistant text (final) — intentionally skipped (already sent).
        # The turn's usage.cost.total (if any) is emitted as a cost event.
        cost = self._extract_cost(obj.get("message", {}))
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
        if cost is not None:
            events.append(PiEvent(kind="cost", cost=cost))
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
