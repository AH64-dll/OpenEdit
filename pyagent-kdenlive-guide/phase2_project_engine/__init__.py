"""PyAgent Phase 2: file-based editor backend for .kdenlive projects.

Public surface (re-exported for backward compatibility):
- EditorBackend, KdenliveFileBackend (the interface + concrete impl)
- All dataclasses from types.py
- All error classes from errors.py
- Catalog from catalog.py

The actual implementation lives in:
- backend.py: ABC + thin KdenliveFileBackend dispatch
- io.py: ProjectTree + load/save
- tracks.py: track/clip navigation helpers
- ops/*.py: per-domain editor operations
- types.py, errors.py, catalog.py, validators.py: pure data/validation
"""
from .backend import (
    EditorBackend,
    KdenliveFileBackend,
    ProjectInfo,
    ClipSummary,
    TrackSummary,
    TransitionSummary,
    MarkerSummary,
    EffectSummary,
    TimelineSummary,
    BackendError,
    ValidationError,
    NotFoundError,
    CatalogError,
)
from .catalog import Catalog


__all__ = [
    "EditorBackend",
    "KdenliveFileBackend",
    "ProjectInfo",
    "ClipSummary",
    "TrackSummary",
    "TransitionSummary",
    "MarkerSummary",
    "EffectSummary",
    "TimelineSummary",
    "BackendError",
    "ValidationError",
    "NotFoundError",
    "CatalogError",
    "Catalog",
]
