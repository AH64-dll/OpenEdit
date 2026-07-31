"""Single source of truth for the on-disk project layout.

Canonical server layout (``serve/projects.py``) stores the edit-graph DB at
``<root>/.open_edit/edit_graph.db``. Older tooling wrote it directly at
``<root>/edit_graph.db``; we read the legacy path only when the canonical
one is absent, and always prefer the canonical path for creation so new
writes land where the server looks for them.
"""
from __future__ import annotations

from pathlib import Path


class ProjectPaths:
    """Resolved paths for one Open Edit project directory.

    ``root`` is the project ROOT directory — the folder that contains
    ``.open_edit/``. The factory accepts either the root itself or a file
    inside it (legacy convention where ``project_path`` was a .kdenlive
    file).
    """

    def __init__(self, root: Path):
        self.root = Path(root)

    @classmethod
    def for_project(cls, project_path: str | Path) -> ProjectPaths:
        """Resolve from a project path: the root itself or a file inside it."""
        p = Path(project_path)
        return cls(p if p.is_dir() else p.parent)

    @classmethod
    def for_workdir(cls, workdir: str | Path) -> ProjectPaths:
        """Resolve from a sandbox workdir.

        A workdir is the directory that directly contains ``edit_graph.db``:
        ``<root>/.open_edit`` in the canonical layout, ``<root>`` in the
        legacy layout.
        """
        workdir = Path(workdir)
        if workdir.name == ".open_edit":
            return cls(workdir.parent)
        return cls(workdir)

    @property
    def db_path(self) -> Path:
        """The project's ``edit_graph.db``.

        Canonical ``<root>/.open_edit/edit_graph.db`` when the canonical
        layout exists (or when the ``.open_edit/`` dir is present, so new
        writes land where the server looks); legacy ``<root>/edit_graph.db``
        is read only when the canonical one is absent.
        """
        canonical = self.root / ".open_edit" / "edit_graph.db"
        if canonical.exists() or (self.root / ".open_edit").is_dir():
            return canonical
        legacy = self.root / "edit_graph.db"
        if legacy.exists():
            return legacy
        return canonical

    @property
    def notes_db_path(self) -> Path:
        """Notes live at the project ROOT (``<root>/notes.db``), NOT inside
        ``.open_edit/`` — see ``serve/projects.py`` which reads them from
        the root."""
        return self.root / "notes.db"

    @property
    def assets_dir(self) -> Path:
        """The project's asset CAS root: ``<root>/.open_edit/assets``."""
        return self.root / ".open_edit" / "assets"

    @property
    def workdir(self) -> Path:
        """The sandbox workdir: the directory that directly contains
        ``edit_graph.db`` (``<root>/.open_edit`` canonical, ``<root>``
        legacy)."""
        return self.db_path.parent
