"""Tests for the taste_events table (Style Memory, Phase 4 stub)."""
from pathlib import Path

import pytest

from open_edit.style.taste_events import TasteEvent, TasteEventStore


def test_append_pull_round_trip(tmp_path: Path) -> None:
    store = TasteEventStore(tmp_path / "taste.db")
    e = TasteEvent(
        op_type="AddTransition",
        proposed_params={"duration_s": 1.0},
        final_params={"duration_s": 0.6},
        action="applied_modified",
    )
    store.append(e)
    pulled = store.pull()
    assert len(pulled) == 1
    assert pulled[0].op_type == "AddTransition"
    assert pulled[0].action == "applied_modified"


def test_pull_respects_max_events(tmp_path: Path) -> None:
    store = TasteEventStore(tmp_path / "taste.db")
    for _ in range(10):
        store.append(TasteEvent(
            op_type="X", proposed_params={}, final_params={},
            action="applied_unmodified",
        ))
    assert len(store.pull(max_events=5)) == 5


def test_purge_removes_events(tmp_path: Path) -> None:
    store = TasteEventStore(tmp_path / "taste.db")
    e1 = TasteEvent(op_type="X", proposed_params={}, final_params={}, action="applied_unmodified")
    e2 = TasteEvent(op_type="Y", proposed_params={}, final_params={}, action="applied_unmodified")
    store.append(e1)
    store.append(e2)
    store.purge([e1.id])
    assert len(store.pull()) == 1


def test_action_must_be_valid_literal() -> None:
    with pytest.raises(ValueError):
        TasteEvent(
            op_type="X", proposed_params={}, final_params={},
            action="totally_made_up",
        )


def test_correction_note_optional() -> None:
    e = TasteEvent(
        op_type="X", proposed_params={}, final_params={},
        action="applied_modified",
    )
    assert e.correction_note is None
