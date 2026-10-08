"""Editable caption source and reusable styles, independent of rendering."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator


class CaptionStyle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    font_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    font_size: float = Field(default=48, ge=8, le=240, allow_inf_nan=False)
    color: str = Field(default="#ffffff", pattern=r"^#[a-fA-F0-9]{6}$")
    background: str = Field(default="#00000099", pattern=r"^#[a-fA-F0-9]{8}$")
    stroke_color: str = Field(default="#000000", pattern=r"^#[a-fA-F0-9]{6}$")
    stroke_width: float = Field(default=1, ge=0, le=12, allow_inf_nan=False)
    x: float = Field(default=0.1, ge=0, le=1, allow_inf_nan=False)
    y: float = Field(default=0.78, ge=0, le=1, allow_inf_nan=False)
    width: float = Field(default=0.8, gt=0, le=1, allow_inf_nan=False)
    align: Literal["left", "center", "right"] = "center"

    @model_validator(mode="after")
    def fits_canvas(self):
        if self.x + self.width > 1.000001:
            raise ValueError("Caption box extends beyond the canvas")
        return self


class CaptionCue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=10000)
    start_sec: float = Field(ge=0, allow_inf_nan=False)
    end_sec: float = Field(gt=0, allow_inf_nan=False)
    style: CaptionStyle = Field(default_factory=CaptionStyle)
    enabled: StrictBool = True
    locked: StrictBool = False

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_sec <= self.start_sec or not self.text.strip():
            raise ValueError("Caption needs text and an end after its start")
        return self
