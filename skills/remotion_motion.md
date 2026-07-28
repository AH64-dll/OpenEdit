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
2. `write_remotion_composition` — write `src/compositions/Foo.tsx` (imports limited to remotion/react).
3. Register the composition in `src/Root.tsx` (via write or free-form).
4. `generate_remotion_composition` — append IR op with props / timing.
5. `trigger_render` with `mode=proxy` or `final` — materialize + melt + ffmpeg burn-in.

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
- Forbidden: `fs`, `child_process`, `net`, `eval`, `process.env`.
- Paths must stay under `.open_edit/remotion/src/`.
