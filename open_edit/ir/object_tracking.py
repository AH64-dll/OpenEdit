"""Editable source-time object tracks. No decoder, model or file dependencies."""
from __future__ import annotations

from bisect import bisect_right
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Unit = Annotated[Number, Field(ge=0, le=1)]
Time = Annotated[Number, Field(ge=0)]


class TrackFrame(BaseModel):
    model_config = ConfigDict(extra='forbid')
    time_sec: Time
    x: Unit
    y: Unit
    width: Annotated[Unit, Field(gt=0)]
    height: Annotated[Unit, Field(gt=0)]
    confidence: Unit = 1
    valid: StrictBool = True
    manual: StrictBool = False

    @model_validator(mode='after')
    def fits(self):
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError('Object boxes must fit inside the source image')
        return self


class TrackedEffect(BaseModel):
    model_config = ConfigDict(extra='forbid')
    effect_id: str = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_.:-]+$')
    kind: Literal['highlight', 'label', 'cover', 'blur', 'pixelate'] = 'highlight'
    enabled: StrictBool = True
    color: str = Field(default='#ffcc55', pattern=r'^#[0-9a-fA-F]{6}$')
    text: str = Field(default='', max_length=500)
    strength: Annotated[Number, Field(ge=1, le=100)] = 20
    padding: Annotated[Number, Field(ge=0, le=.25)] = .01
    offset_x: Annotated[Number, Field(ge=-1, le=1)] = 0
    offset_y: Annotated[Number, Field(ge=-1, le=1)] = 0
    scale: Annotated[Number, Field(ge=.1, le=4)] = 1


class ObjectTrack(BaseModel):
    model_config = ConfigDict(extra='forbid')
    clip_id: str = Field(min_length=1, max_length=128)
    asset_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    label: str = Field(default='Tracked object', min_length=1, max_length=256)
    algorithm: str = Field(default='manual', max_length=128)
    enabled: StrictBool = True
    locked: StrictBool = False
    frames: list[TrackFrame] = Field(min_length=1, max_length=18001)
    effects: list[TrackedEffect] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def ordered(self):
        if any(a.time_sec >= b.time_sec for a, b in zip(self.frames, self.frames[1:], strict=False)):
            raise ValueError('Object track frames must have strictly increasing source times')
        if self.frames[-1].time_sec - self.frames[0].time_sec > 600:
            raise ValueError('A tracking range supports at most 600 seconds')
        if len({e.effect_id for e in self.effects}) != len(self.effects):
            raise ValueError('Tracked effect IDs must be unique')
        return self


def sample_track(track: ObjectTrack, source_time: float) -> TrackFrame | None:
    """Linear boxes, no extrapolation and no interpolation across a lost sample."""
    frames = track.frames
    if not track.enabled or source_time < frames[0].time_sec - 1e-6 or source_time > frames[-1].time_sec + 1e-6:
        return None
    i = max(0, bisect_right(frames, source_time, key=lambda f: f.time_sec) - 1)
    a = frames[i]
    if not a.valid:
        return None
    if i == len(frames) - 1 or abs(source_time - a.time_sec) < 1e-6:
        return a
    b = frames[i + 1]
    if not b.valid:
        return None
    ratio = (source_time - a.time_sec) / (b.time_sec - a.time_sec)
    return a.model_copy(update={k: getattr(a, k) + ratio * (getattr(b, k) - getattr(a, k))
                                for k in ('x', 'y', 'width', 'height', 'confidence')})


def effect_box(frame: TrackFrame, effect: TrackedEffect) -> tuple[float, float, float, float]:
    w = frame.width * effect.scale + effect.padding * 2
    h = frame.height * effect.scale + effect.padding * 2
    x = frame.x + frame.width / 2 - w / 2 + effect.offset_x
    y = frame.y + frame.height / 2 - h / 2 + effect.offset_y
    return max(0, x), max(0, y), min(1, x + w), min(1, y + h)
