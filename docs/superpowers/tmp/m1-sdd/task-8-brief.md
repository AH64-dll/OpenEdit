# Task 8 Brief

### Task 8: Define and prove the host-only Remotion frame-pull protocol

**Files:**
- Create: `open_edit/render/remotion/frame_engine.py`
- Create: `open_edit/render/remotion_frame_server.mjs`
- Modify: `open_edit/render/remotion_scaffold.py`, `package.json`, `package-lock.json`
- Test: `tests/test_remotion_frame_engine.py`, `tests/test_remotion_scaffold.py`

**Interfaces:**
- Consumes: the existing validated Remotion root/entry point and the pinned package versions.
- Produces: an opt-in Python client and a private Node process that returns one requested PNG frame without producing a composition video/CAS artifact.

#### API research required before implementation

The current tree has no programmatic frame engine. `open_edit/render/remotion/renderer.py` shells out to `open_edit/render/remotion_bridge.mjs`, and that bridge invokes the Remotion CLI with an output video path. The root `package.json` already contains `@remotion/renderer`, while the per-project scaffold only declares `@remotion/cli`, `react`, `react-dom`, and `remotion`.

At Remotion `4.0.278`, verify the installed TypeScript declarations and a temporary fixture for these APIs:

```javascript
import {bundle} from "@remotion/bundler";
import {
  selectComposition,
  renderStill,
  renderFrames,
} from "@remotion/renderer";

const serveUrl = await bundle({entryPoint});
const composition = await selectComposition({
  serveUrl,
  id: compositionId,
  inputProps: props,
});
const still = await renderStill({
  composition,
  serveUrl,
  frame,
  inputProps: props,
});
// With no output path, still.buffer must be the PNG/JPEG bytes.
```

Verify that `renderFrames()` accepts a single-frame/range selection and writes an image sequence, and verify the exact `openBrowser()`/browser-instance reuse option before using it. Do not substitute `renderMedia()` for frame pull: it encodes/stitches a whole media output and therefore preserves the rejected bake-then-stitch model. If the pinned declarations do not support the expected `renderStill()` buffer return, fail the API probe with the installed signature and keep the materialized compatibility path; do not invent an undocumented call shape.

- [ ] **Step 1: Write failing protocol tests with a fake frame server.**

```python
def test_frame_client_validates_request_and_reads_exact_png_bytes(tmp_path):
    fake_server = write_fake_frame_server(tmp_path, payload=b"\x89PNGfake")
    client = FramePullClient(
        [sys.executable, str(fake_server)],
        timeout_s=1.0,
    )
    frame = client.request_frame(
        FrameRequest(
            request_id="r1",
            composition_id="TitleCard",
            entry_point="src/index.ts",
            props={"titleText": "Hi"},
            frame=12,
            width=640,
            height=360,
            fps=30.0,
            alpha=False,
        )
    )
    assert frame.content_type == "image/png"
    assert frame.bytes == b"\x89PNGfake"
    client.close()


def test_frame_client_rejects_oversized_or_out_of_range_request():
    with pytest.raises(FrameProtocolError, match="frame"):
        FrameRequest(
            request_id="r",
            composition_id="Comp",
            entry_point="../escape.tsx",
            props={},
            frame=-2,
            width=640,
            height=360,
            fps=30.0,
            alpha=False,
        )
```

- [ ] **Step 2: Run the protocol tests to verify they fail.**

Run: `pytest -q tests/test_remotion_frame_engine.py`

Expected: missing `FramePullClient`, request validation, and server lifecycle failures.

- [ ] **Step 3: Implement a bounded stdin/stdout protocol.**

Use one private process per render job, no TCP listener and no network exposure:

```text
client → server: one JSON line per request
server → client: one JSON header line
server → client: exactly byte_length binary bytes
```

The response header contains `request_id`, `ok`, `content_type`, `byte_length`, `width`, `height`, `frame`, and `remotion_version`; errors contain a bounded `error` string and no props. The Python client must validate entry-point relativity, positive dimensions/fps, non-negative frame, maximum props JSON bytes, maximum response bytes, matching request ID, content type, and exact payload length. It must terminate the process on timeout, malformed framing, EOF, or a nonzero exit.

- [ ] **Step 4: Implement the Node renderer using the verified APIs.**

`remotion_frame_server.mjs` must:

1. Resolve and validate the project root and entry point under `.open_edit/remotion/`.
2. Bundle once per entry point with `@remotion/bundler`.
3. Cache selected composition metadata by `(composition_id, props hash, width, height, fps)`.
4. Call `renderStill()` for the requested frame with `output` omitted and return its buffer.
5. Use PNG for alpha frames; do not transcode through a lossy format.
6. Enforce request dimensions, frame bounds from `durationInFrames`, and a per-request timeout.
7. Exit cleanly when stdin closes or the parent is terminated.

Use `openBrowser()` reuse only if the pinned type signature confirms how to pass the browser to `renderStill()`; otherwise use the verified renderer lifecycle and record the slower path in diagnostics. The process runs only in the host worker; free-form code cannot start it.

- [ ] **Step 5: Add the package/scaffold declarations.**

Add `@remotion/bundler: "4.0.278"` and `@remotion/renderer: "4.0.278"` to the generated project scaffold. Keep the root renderer pin and regenerate the lockfile with:

```bash
npm install --package-lock-only
```

Do not install dependencies into a user project from a free-form operation. The scaffold remains private and preserves the existing Remotion license notice.

- [ ] **Step 6: Add an opt-in engine selector without changing the default.**

Define `OPEN_EDIT_REMOTION_FRAME_ENGINE=materialize|pull`, defaulting to `materialize`. During M1, `pull` is available to the protocol/integration tests only; a normal proxy/final render continues through materialization unless the explicit same-pass feeder in Task 9 is enabled. An explicit unsupported pull request returns a structured `remotion_frame_pull_unavailable` error rather than silently reverting.

- [ ] **Step 7: Run protocol, scaffold, and JavaScript syntax tests.**

Run:

```bash
pytest -q tests/test_remotion_frame_engine.py tests/test_remotion_scaffold.py
node --check open_edit/render/remotion_frame_server.mjs
npm ls @remotion/bundler @remotion/renderer remotion
```

Expected: PASS with all three Remotion packages resolving to `4.0.278`. If Node/Remotion is unavailable, the Python protocol tests still run with the fake server and the API probe reports the missing host dependency explicitly.

- [ ] **Step 8: Commit the frame protocol, not a bake replacement.**

```bash
git add open_edit/render/remotion/frame_engine.py \
  open_edit/render/remotion_frame_server.mjs \
  open_edit/render/remotion_scaffold.py package.json package-lock.json \
  tests/test_remotion_frame_engine.py tests/test_remotion_scaffold.py
git commit -m "feat: add host remotion frame pull protocol"
```

---
