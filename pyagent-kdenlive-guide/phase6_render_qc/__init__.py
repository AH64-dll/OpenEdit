"""Phase 6: render + quality-control tools for the .kdenlive project.

This package wraps melt (for render) and ffmpeg/ffprobe (for thumbnails,
audio levels, black-frame / silence detection). It reuses
``mlt-pipeline/cmd/render`` as its render entry point so PyAgent benefits
from the same ``nice``-level isolation and codec defaults already in use.
"""
