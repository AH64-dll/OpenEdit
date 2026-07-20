"""Pydantic models for Open Edit's IR.

All operations are immutable Pydantic models with stable UUIDs. The
discriminated union is on `kind`, validated via Pydantic's Field(discriminator).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, Field


def new_id() -> str:
    """Return a fresh UUID4 string."""
    return str(uuid.uuid4())


def now_iso8601() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ===== Derived state (Timeline, Track, Clip, Effect) =====

class Effect(BaseModel):
    effect_id: str
    effect_type: str
    params: dict[str, Any] = Field(default_factory=dict)
    keyframes: dict[str, list[tuple[float, float, str]]] = Field(default_factory=dict)


class Clip(BaseModel):
    clip_id: str
    asset_hash: str
    track_id: str
    track_kind: Literal["video", "audio"]
    position_sec: float
    in_point_sec: float
    out_point_sec: float
    effects: list[Effect] = Field(default_factory=list)


class Track(BaseModel):
    track_id: str
    kind: Literal["video", "audio"]
    clips: list[Clip] = Field(default_factory=list)
    effects: list[Effect] = Field(default_factory=list)


class Timeline(BaseModel):
    tracks: list[Track] = Field(default_factory=list)
    duration_sec: float = 0.0


class WordAlignment(BaseModel):
    word: str
    t_start: float
    t_end: float
    confidence: float = 1.0


class Asset(BaseModel):
    asset_hash: str
    original_path: str
    stored_path: str
    type: Literal["video", "audio", "image"]
    duration_sec: float = 0.0
    fps: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    codec: Optional[str] = None
    has_audio: bool = False
    alignment: list[WordAlignment] = Field(default_factory=list)


# ===== Operation base + concrete variants =====

class Operation(BaseModel):
    kind: str  # overridden by each subclass as Literal[...]
    edit_id: str = Field(default_factory=new_id)
    parent_id: Optional[str] = None
    author: Literal["ai", "user"]
    timestamp: str = Field(default_factory=now_iso8601)
    status: Literal["applied", "reverted", "superseded"] = "applied"
    originating_note_id: Optional[str] = None


class AddClipOp(Operation):
    kind: Literal["add_clip"] = "add_clip"
    asset_hash: str
    track_id: str
    track_kind: Literal["video", "audio"] = "video"
    position_sec: float
    in_point_sec: float = 0.0
    out_point_sec: Optional[float] = None
    clip_id: str = Field(default_factory=new_id)


class RemoveClipOp(Operation):
    kind: Literal["remove_clip"] = "remove_clip"
    clip_id: str


class MoveClipOp(Operation):
    kind: Literal["move_clip"] = "move_clip"
    clip_id: str
    new_track_id: str
    new_position_sec: float


class TrimClipOp(Operation):
    kind: Literal["trim_clip"] = "trim_clip"
    clip_id: str
    new_in_point_sec: float
    new_out_point_sec: float


class AddTransitionOp(Operation):
    kind: Literal["add_transition"] = "add_transition"
    clip_a_id: str
    clip_b_id: str
    transition_type: Literal["luma", "dissolve", "wipe", "fade", "cut"]
    duration_sec: float


class RemoveTransitionOp(Operation):
    kind: Literal["remove_transition"] = "remove_transition"
    transition_id: str


class SetTransitionPropertyOp(Operation):
    kind: Literal["set_transition_property"] = "set_transition_property"
    transition_id: str
    prop_name: str
    value: str


class AddEffectOp(Operation):
    kind: Literal["add_effect"] = "add_effect"
    target_kind: Literal["clip", "track"]
    target_id: str
    effect_type: str
    params: dict[str, Any] = Field(default_factory=dict)
    effect_id: str = Field(default_factory=new_id)


class RemoveEffectOp(Operation):
    kind: Literal["remove_effect"] = "remove_effect"
    clip_id: str
    effect_index: int


class SetEffectParamOp(Operation):
    kind: Literal["set_effect_param"] = "set_effect_param"
    clip_id: str
    effect_index: int
    param_name: str
    value: str
    effect_id: str = ""


class SetKeyframeOp(Operation):
    kind: Literal["set_keyframe"] = "set_keyframe"
    effect_id: str
    param: str
    keyframes: list[tuple[float, float, str]]


class RemoveKeyframeOp(Operation):
    kind: Literal["remove_keyframe"] = "remove_keyframe"
    effect_id: str
    param: str
    frame: float


class SlipClipOp(Operation):
    kind: Literal["slip_clip"] = "slip_clip"
    clip_id: str
    delta_sec: float


class RippleDeleteClipOp(Operation):
    kind: Literal["ripple_delete_clip"] = "ripple_delete_clip"
    clip_id: str


class ChangeClipSpeedOp(Operation):
    kind: Literal["change_clip_speed"] = "change_clip_speed"
    clip_id: str
    rate: float


class SplitClipOp(Operation):
    kind: Literal["split_clip"] = "split_clip"
    clip_id: str
    at_sec: float
    left_clip_id: str = Field(default_factory=new_id)
    right_clip_id: str = Field(default_factory=new_id)


class ReplaceClipSourceOp(Operation):
    kind: Literal["replace_clip_source"] = "replace_clip_source"
    clip_id: str
    new_asset_hash: str


class SetClipSpeedRampOp(Operation):
    kind: Literal["set_clip_speed_ramp"] = "set_clip_speed_ramp"
    clip_id: str
    keyframes: list[dict[str, Any]] = Field(default_factory=list)


class SetAudioGainOp(Operation):
    """First-class audio op. NOT a side-effect of video."""
    kind: Literal["set_audio_gain"] = "set_audio_gain"
    clip_id: str
    gain_db: float
    keyframe_op_id: Optional[str] = None


class NormalizeAudioOp(Operation):
    """First-class audio normalization."""
    kind: Literal["normalize_audio"] = "normalize_audio"
    target_kind: Literal["clip", "track", "project"]
    target_id: str
    target_dbfs: float = -16.0


class GroupEditsOp(Operation):
    kind: Literal["group_edits"] = "group_edits"
    edit_ids: list[str]
    label: str


class UngroupEditsOp(Operation):
    kind: Literal["ungroup_edits"] = "ungroup_edits"
    label: str


class RawMltXmlOp(Operation):
    kind: Literal["raw_mlt_xml"] = "raw_mlt_xml"
    xml: str
    description: str


class FreeFormCodeOp(Operation):
    kind: Literal["free_form_code"] = "free_form_code"
    code: str
    timeout_sec: int = 30
    mem_mb: int = 512
    label: Optional[str] = None


OperationUnion = Annotated[
    Union[
        AddClipOp, RemoveClipOp, MoveClipOp, TrimClipOp,
        AddTransitionOp, RemoveTransitionOp, SetTransitionPropertyOp,
        AddEffectOp, RemoveEffectOp, SetEffectParamOp,
        SetKeyframeOp, RemoveKeyframeOp,
        SlipClipOp, RippleDeleteClipOp, ChangeClipSpeedOp,
        SplitClipOp, ReplaceClipSourceOp, SetClipSpeedRampOp,
        SetAudioGainOp, NormalizeAudioOp,
        GroupEditsOp, UngroupEditsOp,
        RawMltXmlOp, FreeFormCodeOp,
    ],
    Field(discriminator="kind"),
]


class Project(BaseModel):
    project_id: str = Field(default_factory=new_id)
    name: str
    workdir: Optional[Path] = None
    created_at: str = Field(default_factory=now_iso8601)
    assets: dict[str, Asset] = Field(default_factory=dict)
    edit_graph: list[OperationUnion] = Field(default_factory=list)
