"""In-process IR API for free-form Python code (sandbox side).

Phase 3 Task 4: real implementation. Each method builds one Pydantic op with
parent_id stamped at construction time and appends to a buffer (which the
sandbox wires to ops.jsonl on disk).

Phase 4 Task 1: every method also accepts optional `originating_note_id`
(default None). If the caller omits it, the IR instance's constructor-level
value (set by the bootstrap) is used. This lets the sandbox tag every op
produced in response to a note with the source note_id.
"""
from __future__ import annotations

from typing import Any, Optional, Protocol

from open_edit.ir.types import (
    AddClipOp, AddEffectOp, AddTransitionOp, FreeFormCodeOp, GroupEditsOp,
    MoveClipOp, NormalizeAudioOp, RawMltXmlOp, RemoveClipOp, SetAudioGainOp,
    SetKeyframeOp, TrimClipOp, new_id,
)


class SupportsAppend(Protocol):
    """Anything with a single-arg `append` (list, _FlushingBuffer, ...)."""

    def append(self, __x: Any) -> None: ...


class IR:
    """Free-form Python IR API. Each method appends one Pydantic op to the buffer.

    The buffer is any SupportsAppend (list, _FlushingBuffer, etc.). The sandbox
    wires a _FlushingBuffer that writes each op to ops.jsonl on append.
    """

    def __init__(
        self,
        ops_buffer: SupportsAppend,
        project_id: str,
        parent_op_id: str,
        originating_note_id: Optional[str] = None,
    ):
        self._ops = ops_buffer
        self._project_id = project_id
        self._parent_op_id = parent_op_id
        self._originating_note_id = originating_note_id

    def _note_id(self, originating_note_id: Optional[str]) -> Optional[str]:
        """Caller-supplied value wins; else fall back to the IR-level value."""
        return originating_note_id if originating_note_id is not None else self._originating_note_id

    def add_clip(
        self, asset_hash: str, track_id: str, position_sec: float,
        in_point_sec: float = 0.0, out_point_sec: float | None = None,
        originating_note_id: Optional[str] = None,
    ) -> str:
        """Append AddClipOp; return generated clip_id."""
        clip_id = new_id()
        op = AddClipOp(
            edit_id=new_id(),
            author="ai",
            parent_id=self._parent_op_id,
            clip_id=clip_id,
            asset_hash=asset_hash,
            track_id=track_id,
            position_sec=position_sec,
            in_point_sec=in_point_sec,
            out_point_sec=out_point_sec,
            originating_note_id=self._note_id(originating_note_id),
        )
        self._ops.append(op)
        return clip_id

    def trim_clip(
        self, clip_id: str, in_point_sec: float, out_point_sec: float,
        originating_note_id: Optional[str] = None,
    ) -> None:
        op = TrimClipOp(
            edit_id=new_id(),
            author="ai",
            parent_id=self._parent_op_id,
            clip_id=clip_id,
            new_in_point_sec=in_point_sec,
            new_out_point_sec=out_point_sec,
            originating_note_id=self._note_id(originating_note_id),
        )
        self._ops.append(op)

    def move_clip(
        self, clip_id: str, new_track_id: str, new_position_sec: float,
        originating_note_id: Optional[str] = None,
    ) -> None:
        op = MoveClipOp(
            edit_id=new_id(),
            author="ai",
            parent_id=self._parent_op_id,
            clip_id=clip_id,
            new_track_id=new_track_id,
            new_position_sec=new_position_sec,
            originating_note_id=self._note_id(originating_note_id),
        )
        self._ops.append(op)

    def remove_clip(
        self, clip_id: str,
        originating_note_id: Optional[str] = None,
    ) -> None:
        op = RemoveClipOp(
            edit_id=new_id(),
            author="ai",
            parent_id=self._parent_op_id,
            clip_id=clip_id,
            originating_note_id=self._note_id(originating_note_id),
        )
        self._ops.append(op)

    def add_transition(
        self, clip_a_id: str, clip_b_id: str, transition_type: str, duration_sec: float,
        originating_note_id: Optional[str] = None,
    ) -> None:
        op = AddTransitionOp(
            edit_id=new_id(),
            author="ai",
            parent_id=self._parent_op_id,
            clip_a_id=clip_a_id,
            clip_b_id=clip_b_id,
            transition_type=transition_type,
            duration_sec=duration_sec,
            originating_note_id=self._note_id(originating_note_id),
        )
        self._ops.append(op)

    def add_effect(
        self, target_kind: str, target_id: str, effect_type: str, params: dict[str, Any],
        originating_note_id: Optional[str] = None,
    ) -> None:
        op = AddEffectOp(
            edit_id=new_id(),
            author="ai",
            parent_id=self._parent_op_id,
            target_kind=target_kind,
            target_id=target_id,
            effect_type=effect_type,
            params=params,
            originating_note_id=self._note_id(originating_note_id),
        )
        self._ops.append(op)

    def set_keyframe(
        self, effect_id: str, param: str, keyframes: list[tuple[float, float, str]],
        originating_note_id: Optional[str] = None,
    ) -> None:
        op = SetKeyframeOp(
            edit_id=new_id(),
            author="ai",
            parent_id=self._parent_op_id,
            effect_id=effect_id,
            param=param,
            keyframes=keyframes,
            originating_note_id=self._note_id(originating_note_id),
        )
        self._ops.append(op)

    def set_audio_gain(
        self, clip_id: str, gain_db: float,
        originating_note_id: Optional[str] = None,
    ) -> None:
        op = SetAudioGainOp(
            edit_id=new_id(),
            author="ai",
            parent_id=self._parent_op_id,
            clip_id=clip_id,
            gain_db=gain_db,
            originating_note_id=self._note_id(originating_note_id),
        )
        self._ops.append(op)

    def normalize_audio(
        self, target_kind: str, target_id: str, target_dbfs: float,
        originating_note_id: Optional[str] = None,
    ) -> None:
        op = NormalizeAudioOp(
            edit_id=new_id(),
            author="ai",
            parent_id=self._parent_op_id,
            target_kind=target_kind,
            target_id=target_id,
            target_dbfs=target_dbfs,
            originating_note_id=self._note_id(originating_note_id),
        )
        self._ops.append(op)

    def group_edits(
        self, edit_ids: list[str], label: str,
        originating_note_id: Optional[str] = None,
    ) -> None:
        op = GroupEditsOp(
            edit_id=new_id(),
            author="ai",
            parent_id=self._parent_op_id,
            edit_ids=edit_ids,
            label=label,
            originating_note_id=self._note_id(originating_note_id),
        )
        self._ops.append(op)

    def raw_mlt_xml(
        self, xml: str, description: str,
        originating_note_id: Optional[str] = None,
    ) -> None:
        op = RawMltXmlOp(
            edit_id=new_id(),
            author="ai",
            parent_id=self._parent_op_id,
            xml=xml,
            description=description,
            originating_note_id=self._note_id(originating_note_id),
        )
        self._ops.append(op)

    def free_form_code(
        self, code: str,
        originating_note_id: Optional[str] = None,
    ) -> None:
        op = FreeFormCodeOp(
            edit_id=new_id(),
            author="ai",
            parent_id=self._parent_op_id,
            code=code,
            originating_note_id=self._note_id(originating_note_id),
        )
        self._ops.append(op)
