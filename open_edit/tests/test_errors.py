"""Unit tests for the unified error envelope (open_edit.serve.errors)."""
from __future__ import annotations

from open_edit.serve.errors import ErrorCodes, make_error, wrap_exception


def test_make_error_shape_and_defaults() -> None:
    result = make_error(ErrorCodes.NOT_FOUND, "missing")
    assert result == {
        "error": {
            "code": "not_found",
            "message": "missing",
            "retriable": False,
            "details": None,
            "request_id": None,
            "docs_url": None,
        }
    }


def test_make_error_all_fields() -> None:
    result = make_error(
        ErrorCodes.RATE_LIMITED,
        "slow down",
        retriable=True,
        details={"retry_after": 5},
        request_id="req-123",
        docs_url="https://example.com/docs",
    )
    err = result["error"]
    assert err["code"] == "rate_limited"
    assert err["message"] == "slow down"
    assert err["retriable"] is True
    assert err["details"] == {"retry_after": 5}
    assert err["request_id"] == "req-123"
    assert err["docs_url"] == "https://example.com/docs"


def test_wrap_exception_captures_message() -> None:
    result = wrap_exception(ValueError("boom"))
    assert result["error"]["code"] == "internal"
    assert result["error"]["message"] == "boom"
    assert result["error"]["retriable"] is False


def test_wrap_exception_custom_code_and_kwargs() -> None:
    result = wrap_exception(
        RuntimeError("provider down"),
        ErrorCodes.PROVIDER_ERROR,
        retriable=True,
        request_id="r-9",
    )
    err = result["error"]
    assert err["code"] == "provider_error"
    assert err["message"] == "provider down"
    assert err["retriable"] is True
    assert err["request_id"] == "r-9"


def test_error_codes_values() -> None:
    assert ErrorCodes.VALIDATION_FAILED == "validation_failed"
    assert ErrorCodes.NOT_FOUND == "not_found"
    assert ErrorCodes.CONFLICT == "conflict"
    assert ErrorCodes.PERMISSION_DENIED == "permission_denied"
    assert ErrorCodes.AUTH_REQUIRED == "auth_required"
    assert ErrorCodes.SANDBOX_UNAVAILABLE == "sandbox_unavailable"
    assert ErrorCodes.RENDER_FAILED == "render_failed"
    assert ErrorCodes.PROVIDER_ERROR == "provider_error"
    assert ErrorCodes.RATE_LIMITED == "rate_limited"
    assert ErrorCodes.TIMEOUT == "timeout"
    assert ErrorCodes.INTERNAL == "internal"
