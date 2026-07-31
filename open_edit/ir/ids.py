"""Shared id and timestamp generators.

Single source of truth for UUIDs and ISO-8601 timestamps across ir,
storage, and serve. Formats below are frozen to match the historical
implementations (``str(uuid.uuid4())`` for new_id, full-UTC ``isoformat()``
for now_iso8601, ``note_<hex12>`` / ``v_<hex12>`` for note/version ids) —
do not change them without a migration.
"""

import uuid
from datetime import datetime, timezone


def new_id() -> str:
    """Return a fresh UUID4 string."""
    return str(uuid.uuid4())


def now_iso8601() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def new_note_id() -> str:
    """Return a fresh review-note id (``note_<hex12>``)."""
    return f"note_{uuid.uuid4().hex[:12]}"


def new_version_id() -> str:
    """Return a fresh render-version id (``v_<hex12>``)."""
    return f"v_{uuid.uuid4().hex[:12]}"
