from __future__ import annotations

from .project import ToolDef


_V = {"type": "string"}
_O = {"type": "string"}
_N = {"type": "number", "minimum": 0}
_I = {"type": "integer", "minimum": 0}
RENDER = ToolDef(
    name="pyagent_render",
    label="Render project",
    description="Render the .kdenlive project to an MP4. mode='proxy' (640x360, fast) is the default for iteration; mode='final' uses the project's own profile and is slow. Optional in_sec/out_sec for a ranged render.",
    is_mutating=False,
    parameters_schema={
        "mode": {"type": "string", "enum": ["proxy", "final"], "default": "proxy"},
        "output": _O, "in_sec": _N, "out_sec": _N,
    },
    required=("mode", "output"),
)
GET_THUMBNAIL = ToolDef(
    name="pyagent_get_thumbnail",
    label="Get thumbnail",
    description="Extract a single JPEG frame at the given timestamp. Output is capped at <=480px on the long edge, ~70 quality, <250KB. Use this to visually verify a frame without pulling full-resolution data.",
    is_mutating=False,
    parameters_schema={"video": _V, "timestamp_sec": _N, "output": _O},
    required=("video", "timestamp_sec", "output"),
)
GET_QC_CROP = ToolDef(
    name="pyagent_get_qc_crop",
    label="Get QC crop",
    description="Extract a small crop of the frame at the given timestamp. region = {x, y, w, h} in source pixels. Same size/quality caps as get_thumbnail.",
    is_mutating=False,
    parameters_schema={
        "video": _V, "timestamp_sec": _N,
        "region": {
            "type": "object",
            "properties": {
                "x": _I, "y": _I,
                "w": {"type": "integer", "minimum": 1},
                "h": {"type": "integer", "minimum": 1},
            },
            "required": ["x", "y", "w", "h"],
        },
        "output": _O,
    },
    required=("video", "timestamp_sec", "region", "output"),
)
LIST_BLACK_FRAMES = ToolDef(
    name="pyagent_list_black_frames",
    label="List black frames",
    description="Return ranges where the average luma is below `threshold` (0..1) for at least `min_sec` consecutive seconds. Cheap deterministic check; use before pulling thumbnails.",
    is_mutating=False,
    parameters_schema={
        "video": _V, "in_sec": _N, "out_sec": _N,
        "threshold": {"type": "number", "minimum": 0, "maximum": 1},
        "min_sec": _N,
    },
    required=("video",),
)
LIST_SILENCE = ToolDef(
    name="pyagent_list_silence",
    label="List silence",
    description="Return ranges where audio falls below `threshold_db` dB for at least `min_sec` consecutive seconds. Cheap deterministic check.",
    is_mutating=False,
    parameters_schema={
        "video": _V, "in_sec": _N, "out_sec": _N,
        "threshold_db": {"type": "number", "maximum": 0},
        "min_sec": _N,
    },
    required=("video",),
)
GET_AUDIO_LEVELS = ToolDef(
    name="pyagent_get_audio_levels",
    label="Get audio levels",
    description="Return RMS and peak dB for the audio over the requested range. Numeric only — no waveform image.",
    is_mutating=False,
    parameters_schema={"video": _V, "in_sec": _N, "out_sec": _N},
    required=("video",),
)
TOOLS = [RENDER, GET_THUMBNAIL, GET_QC_CROP, LIST_BLACK_FRAMES, LIST_SILENCE, GET_AUDIO_LEVELS]
