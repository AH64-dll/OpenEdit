"""Motion graphics templates, one per narrative beat type."""
from open_edit.agent.skills.motion_graphics.templates.button import button_cta
from open_edit.agent.skills.motion_graphics.templates.cost import cost_warning
from open_edit.agent.skills.motion_graphics.templates.hook import hook_fade_text
from open_edit.agent.skills.motion_graphics.templates.mechanism import (
    mechanism_diagram,
)
from open_edit.agent.skills.motion_graphics.templates.scope import scope_zoom_text
from open_edit.agent.skills.motion_graphics.templates.tease import tease_glimpse
from open_edit.agent.skills.motion_graphics.templates.turn import turn_slide_text


__all__ = [
    "button_cta",
    "cost_warning",
    "hook_fade_text",
    "mechanism_diagram",
    "scope_zoom_text",
    "tease_glimpse",
    "turn_slide_text",
]
