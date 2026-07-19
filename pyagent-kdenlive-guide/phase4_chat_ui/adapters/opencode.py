"""OpenCodeAdapter — shells the `opencode` CLI and parses its JSON event stream."""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from typing import Any, AsyncIterator, Callable

from phase4_chat_ui.types import PiEvent


def _extract_cost(obj: dict) -> float | None:
    """Pull USD cost from a pi/opencode usage.cost.total field, if present."""
    usage = obj.get("usage") if isinstance(obj, dict) else None
    if not isinstance(usage, dict):
        return None
    cost = (usage.get("cost") or {}).get("total")
    if isinstance(cost, (int, float)) and cost > 0:
        return float(cost)
    return None


def _default_models(cmd: list[str]) -> str:
    """Shell `opencode models` and return its stdout as a string."""
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return result.stdout


async def _default_run_cmd(cmd: list[str]):
    """Default subprocess launcher: shells the given command list."""
    return await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


class OpenCodeAdapter:
    """Adapter that shells the `opencode` CLI (`opencode run --format json`)."""

    app_id = "opencode"

    def __init__(
        self,
        model: str,
        project: str,
        session_id: str,
        models_cmd_fn: Callable[[list[str]], str] | None = None,
        run_cmd_fn: Callable[..., Any] | None = None,
    ) -> None:
        self.model = model
        self.project = project
        self.session_id = session_id
        self._models_cmd_fn = models_cmd_fn if models_cmd_fn is not None else _default_models
        self._run_cmd_fn = run_cmd_fn if run_cmd_fn is not None else _default_run_cmd
        self._proc = None

    def available(self) -> bool:
        return shutil.which("opencode") is not None

    def list_models(self) -> list[dict]:
        raw = self._models_cmd_fn(["opencode", "models"])
        models: list[dict] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            models.append({"id": line, "name": line})
        return models

    async def run_prompt(self, text: str, image_paths: list[str] | None = None) -> AsyncIterator[PiEvent]:
        cmd = [
            "opencode", "run", "--format", "json", "--auto",
            "--model", self.model,
        ]
        if image_paths:
            for ip in image_paths:
                cmd += ["--file", ip]
        cmd += [text]

        try:
            proc = await self._run_cmd_fn(cmd)
        except FileNotFoundError:
            yield PiEvent(kind="error", text="opencode binary not found")
            return

        self._proc = proc
        try:
            assert proc.stdout is not None
            async for raw in proc.stdout:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event = self._to_event(obj)
                if event is not None:
                    yield event
            yield PiEvent(kind="done")
        except asyncio.CancelledError:
            self.stop()
            raise
        finally:
            if proc.returncode is None:
                try:
                    proc.kill()
                except Exception:
                    pass
            self._proc = None

    def stop(self) -> None:
        if self._proc is not None and self._proc.returncode is None:
            try:
                self._proc.kill()
            except Exception:
                pass

    @staticmethod
    def _to_event(obj: dict) -> PiEvent | None:
        """Map an `opencode run --format json` event to a normalized PiEvent.

        Real opencode event schema (observed):
          {"type":"step_start", ...}                       -> ignore
          {"type":"text","text":"...", ...}                 -> assistant text delta
          {"type":"tool_use","part":{                      -> tool call
              "type":"tool","tool":"bash",
              "state":{"status":"completed",
                       "input":{"command":"ls"},
                       "output":"..."}}}
          {"type":"step_finish", ...}                      -> ignore (done emitted after stream)
          {"type":"error","error":"..."}                   -> error
        """
        etype = obj.get("type")

        if etype == "error" or "error" in obj:
            err = obj.get("error") or obj.get("message") or "unknown error"
            return PiEvent(kind="error", text=str(err))

        if etype == "text":
            # The text string lives in different places depending on whether
            # opencode is attached to a TTY: top-level "text", or nested
            # under "part"."text" when run headless (subprocess, no TTY).
            text = obj.get("text")
            if not isinstance(text, str):
                text = (obj.get("part") or {}).get("text")
            if isinstance(text, str) and text:
                return PiEvent(kind="message_delta", role="assistant", text=text)
            return None

        # opencode streams a "usage" / cost object on step_finish / final
        # events. Surface any positive USD total as a cost event.
        cost = _extract_cost(obj)
        if cost is not None:
            return PiEvent(kind="cost", cost=cost)

        if etype == "tool_use":
            part = obj.get("part") or {}
            tool = part.get("tool")
            state = part.get("state") or {}
            args = state.get("input") or {}
            result = state.get("output")
            if tool:
                return PiEvent(
                    kind="tool",
                    tool=str(tool),
                    args=args if isinstance(args, dict) else {"input": args},
                    result=result,
                )
            return None

        # step_start / step_finish / unknown -> no UI event
        return None
