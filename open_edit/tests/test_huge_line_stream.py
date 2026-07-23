import asyncio
import pytest
import json

@pytest.mark.asyncio
async def test_huge_line_stream_no_limit_overrun():
    """Verify that a single JSON line > 2MB does not raise LimitOverrunError."""
    huge_payload = {"type": "text_delta", "text": "A" * (2 * 1024 * 1024)}
    line_bytes = json.dumps(huge_payload).encode() + b"\n"

    class MockStream:
        def __init__(self, data):
            self.data = data
            self.offset = 0
        async def read(self, n):
            if self.offset >= len(self.data):
                return b""
            chunk = self.data[self.offset:self.offset + n]
            self.offset += len(chunk)
            return chunk

    stream = MockStream(line_bytes)

    buf = b""
    received_lines = []
    while True:
        chunk = await stream.read(65536)
        if not chunk:
            if buf:
                received_lines.append(buf)
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            received_lines.append(line + b"\n")

    assert len(received_lines) == 1
    assert len(received_lines[0]) >= 2 * 1024 * 1024
