import pytest
from phase2_project_engine.errors import (
    BackendError, ValidationError, NotFoundError, CatalogError,
    validation_error,
)


def test_validation_error_carries_fix_hint():
    e = validation_error("track_index out of range", "set track_index=0..3")
    assert "track_index out of range" in str(e)
    assert "fix:" in str(e)
    assert "set track_index=0..3" in str(e)


def test_validation_error_appends_fix_only_once():
    e = validation_error("already has fix: here", "another hint")
    # No duplicate "fix:" lines
    assert str(e).count("fix:") == 1


def test_not_found_inherits_backend():
    assert issubclass(NotFoundError, BackendError)


def test_catalog_error_inherits_backend():
    assert issubclass(CatalogError, BackendError)


def test_can_catch_all_with_backend_error():
    for cls in (ValidationError, NotFoundError, CatalogError):
        try:
            raise cls("boom")
        except BackendError as e:
            assert "boom" in str(e)
