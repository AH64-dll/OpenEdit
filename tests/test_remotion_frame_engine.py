"""Tests for the host-only Remotion frame-pull protocol."""
from __future__ import annotations

import json
import sys
import textwrap
import time
from pathlib import Path

import pytest

from open_edit.render.remotion.frame_engine import (
    FrameProtocolError,
    FramePullClient,
    FrameRequest,
    frame_engine_status,
    select_frame_engine,
)


def _write_fake_frame_server(
    tmp_path: Path,
    *,
    payload: bytes = b"\x89PNGfake",
    body: str | None = None,
) -> Path:
    server = tmp_path / "fake_frame_server.py"
    default_body = """
    for line in sys.stdin:
        request = json.loads(line)
        header = {
            "request_id": request["request_id"],
            "ok": True,
            "content_type": "image/png",
            "byte_length": len(payload),
            "width": request["width"],
            "height": request["height"],
            "frame": request["frame"],
            "remotion_version": "4.0.278",
        }
        sys.stdout.buffer.write(
            (json.dumps(header) + "\\n").encode("utf-8") + payload
        )
        sys.stdout.buffer.flush()
    """
    server_body = textwrap.dedent(body or default_body).strip()
    server.write_text(
        f"import json\nimport sys\n\npayload = {payload!r}\n\n{server_body}\n",
        encoding="utf-8",
    )
    return server


def _request(
    *,
    props: dict[str, object] | None = None,
    entry_point: str = "src/index.ts",
    frame: int = 12,
) -> FrameRequest:
    return FrameRequest(
        request_id="r1",
        composition_id="TitleCard",
        entry_point=entry_point,
        props=props or {"titleText": "Hi"},
        frame=frame,
        width=640,
        height=360,
        fps=30.0,
        alpha=False,
    )


def test_frame_client_validates_request_and_reads_exact_png_bytes(tmp_path: Path):
    fake_server = _write_fake_frame_server(tmp_path, payload=b"\x89PNGfake")
    client = FramePullClient(
        [sys.executable, str(fake_server)],
        timeout_s=1.0,
    )
    frame = client.request_frame(_request())

    assert frame.content_type == "image/png"
    assert frame.bytes == b"\x89PNGfake"
    assert frame.width == 640
    assert frame.height == 360
    client.close()


def test_frame_request_rejects_out_of_range_frame_before_path_validation():
    with pytest.raises(FrameProtocolError, match="frame"):
        _request(entry_point="../escape.tsx", frame=-2)


def test_frame_request_rejects_non_relative_entry_point():
    with pytest.raises(FrameProtocolError, match="entry.point"):
        _request(entry_point="/tmp/escape.tsx", frame=0)


def test_frame_client_rejects_oversized_props_json(tmp_path: Path):
    fake_server = _write_fake_frame_server(tmp_path)
    client = FramePullClient(
        [sys.executable, str(fake_server)],
        timeout_s=1.0,
        max_props_json_bytes=32,
    )

    with pytest.raises(FrameProtocolError, match="props"):
        client.request_frame(_request(props={"titleText": "x" * 100}))

    client.close()


def test_frame_client_rejects_response_with_wrong_payload_length(tmp_path: Path):
    fake_server = _write_fake_frame_server(
        tmp_path,
        payload=b"\x89PNGfake",
        body="""
        for line in sys.stdin:
            request = json.loads(line)
            header = {
                "request_id": request["request_id"],
                "ok": True,
                "content_type": "image/png",
                "byte_length": len(payload) + 1,
                "width": request["width"],
                "height": request["height"],
                "frame": request["frame"],
                "remotion_version": "4.0.278",
            }
            sys.stdout.buffer.write(
                (json.dumps(header) + "\\n").encode("utf-8") + payload
            )
            sys.stdout.buffer.flush()
        """,
    )
    client = FramePullClient([sys.executable, str(fake_server)], timeout_s=0.2)

    with pytest.raises(FrameProtocolError, match="payload|EOF|closed|timed out"):
        client.request_frame(_request())

    client.close()


def test_frame_client_terminates_hung_server_on_timeout(tmp_path: Path):
    fake_server = _write_fake_frame_server(
        tmp_path,
        body="""
        for _line in sys.stdin:
            time.sleep(2)
        """,
    )
    # The fake script needs this import only for the timeout body.
    fake_server.write_text(
        fake_server.read_text(encoding="utf-8").replace(
            "import sys\n", "import sys\nimport time\n"
        ),
        encoding="utf-8",
    )
    client = FramePullClient([sys.executable, str(fake_server)], timeout_s=0.05)

    started = time.monotonic()
    with pytest.raises(FrameProtocolError, match="timed out"):
        client.request_frame(_request())
    assert time.monotonic() - started < 1.0

    client.close()


def test_frame_engine_defaults_to_materialize_and_rejects_unsupported_pull(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("OPEN_EDIT_REMOTION_FRAME_ENGINE", raising=False)
    assert select_frame_engine() == "materialize"

    monkeypatch.setenv("OPEN_EDIT_REMOTION_FRAME_ENGINE", "pull")
    with pytest.raises(FrameProtocolError, match="remotion_frame_pull_unavailable"):
        select_frame_engine()

    assert select_frame_engine(allow_pull=True) == "pull"
    assert frame_engine_status() == {
        "ok": False,
        "error_code": "remotion_frame_pull_unavailable",
        "error": "remotion_frame_pull_unavailable: same-pass frame feeding is not enabled",
    }
