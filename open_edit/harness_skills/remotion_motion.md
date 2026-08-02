# Remotion motion graphics in Open Edit

## When to use which backend

| Need | Backend | Op / tool |
|---|---|---|
| Lower third / simple `{{name}}` banner | HyperFrames | `AddHtmlOverlayOp` / `ir.add_html_overlay` |
| Kinetic titles, springs, charts, code anim | **Remotion** | `AddRemotionCompositionOp` / `generate_remotion_composition` |
| Quick procedural beat fill | moviepy templates | `generate_visual_for_segment` |

Remotion compositions are **materialized to CAS clips before melt**.
Proxy/final then **ffmpeg-burns** those clips onto the melt output (MLT
multitrack composite of Remotion is not the trusted path). Do **not** rely
on `mode=overlay` for Remotion.

If Remotion materialization or burn-in fails, the render **fails** (no silent omission).

## License

Remotion is free for individuals and orgs ≤3 employees. Larger orgs need a
Company / Automators license. See `docs/REMOTION_LICENSE.md`.

## Agent workflow

1. `init_remotion_project` — scaffold `.open_edit/remotion/` (idempotent).
2. `write_remotion_composition` — write `src/compositions/Foo.tsx` (imports allow-listed to `remotion`, `@remotion/*`, `react`, `react-dom`, and relative `./` / `../` modules).
3. Register the composition in `src/Root.tsx` (via write or free-form).
4. `generate_remotion_composition` — append IR op with props / timing.
5. `trigger_render` with `mode=proxy` or `final` — materialize + melt + ffmpeg burn-in.

## Transparent overlays and proxy cost

`alpha` is the per-pixel transparency mask that lets a popup coexist with
the original video. ProRes 4444 stores RGB plus that mask and remains the
correctness fallback. With `OPEN_EDIT_ALPHA_MODE=auto`, Open Edit first runs
an FFmpeg decode-and-composite probe and uses VP8/VP9 alpha only when the
probe proves the mask survives; otherwise it selects ProRes automatically.
Proxy renders use the `fast_proxy` 640x360 profile, fast encoder tier, and
lower audio bitrate. Alpha intermediates use those same proxy dimensions.

## Props example

```json
{
  "composition_id": "TitleCard",
  "entry_point": "src/index.ts",
  "position_sec": 0,
  "duration_sec": 3,
  "props": { "titleText": "Welcome" },
  "track_id": "video_graphics",
  "alpha": false
}
```

## Security

- No agent-driven `npm install`.
- `validate_composition_source` rejects (mirror of `render/remotion_scaffold.py`
  `FORBIDDEN_IMPORT_PATTERNS`): `node:fs`, `node:child_process`, `node:net`,
  `node:http`, `node:https`, bare `child_process`, `fs/promises`, `fs` /
  `child_process` / `net` imports, `require("fs")` / `require("child_process")`,
  `process.env`, `eval(`, `Function(`.
- Any import line must match the allow-list (`remotion`, `@remotion/`, `react`,
  `react-dom`, or a relative `./` / `../` path) or it is rejected.
- Paths must stay under `.open_edit/remotion/src/`.
