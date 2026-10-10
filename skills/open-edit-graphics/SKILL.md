---
name: open-edit-graphics
description: >-
  Motion graphics in Open Edit: Diffusion JSX (default for titles, lower thirds,
  shapes, animated text), HyperFrames HTML overlays (advanced HTML/CSS/JS), and
  legacy Remotion migration. Exact element/prop grammar and the overlay timing
  contract. Load before creating or editing any graphic.
---

# Graphics

Pick the engine by need, not habit:

1. **Diffusion** (default): titles, lower thirds, shapes, images, simple
   animation. Validated, editable later by element ID, no browser code.
2. **HyperFrames overlay**: only when you need real HTML/CSS/JS (data-driven
   layouts, custom fonts/CSS, GSAP choreography).
3. **Remotion**: never for new work; migration input only.

`get_readiness` tells you whether `graphics` (Diffusion) or the optional HTML
package is installed. Don't read engine source or `node_modules` to learn
these contracts; they are below.

## Diffusion workflow

1. `query_project {query: get_graphics_view, params: {include_source: true}}`
   gives the current or default source plus `graph_revision`.
2. `trigger_render {mode: graphics, expected_revision, graphics: {source,
   duration_sec, fps}}` (duration ≤ 60 s, fps 1–60, ≤ 1800 frames). Poll the job.
3. Review, then `edit_project {operation: commit_graphics, params: {job_id,
   expected_revision, track_id?, position_sec?, clip_id?}}`.
4. Later tweaks: `apply_graphics_edits {expected_revision, document_id, edits}`
   with `{kind:"set", source:"index.tsx:<id>", props:{x:144}}` or
   `{kind:"text", source:"index.tsx:<id>", text:"Hi"}`; no full source needed.

### JSX grammar (enforced by the compiler)

Exactly `export default function Graphics() { return <stage>…</stage>; }`.
All props are literals; every element needs a unique `id`.

```jsx
export default function Graphics() {
  return <stage id="s">
    <scene id="sc" width={1920} height={1080} active>
      <rect id="panel" x={80} y={820} width={900} height={160} fill="#15354d" cornerRadius={20} end={4}>
        <animation id="panel-in" type="slideUp" phase="in" duration={0.5} />
      </rect>
      <text id="title" x={120} y={860} width={820} height={80} fontFamily="OpenEdit Sans"
            fontSize={56} color="#ffffff" end={4}>Your title<animation id="title-in" type="fade" phase="in" duration={0.6} delay={0.2} /></text>
    </scene>
  </stage>;
}
```

- Nesting: `stage > scene > (group | rect | text | image | sequence)`;
  `group`/`rect`/`text`/`image` may contain `animation` and `keyframeTrack`;
  `sequence` holds groups/shapes and its children may use `transition`.
- Common props: `x y width height rotation scale scaleX scaleY opacity
  cornerRadius start end hidden fill` (`start`/`end` seconds, 0–60).
- `text`: `fontFamily="OpenEdit Sans"` (required), `fontSize`, `fontWeight`,
  `color`, `textAlign`, `textBaseline`. `image`: `src="asset://<64-hex hash>"`, `fit`.
- `animation`: `type` = `fade grow shrink slideLeft slideRight slideUp slideDown spin`,
  `phase` = `in`|`out`, `duration`, `delay`.
- `keyframeTrack property` = `x y width height rotation scale opacity color`,
  containing `<keyframe id time value easing />`; easing `linear easeIn easeOut
  easeInOut` or `cubicBezier(x1,y1,x2,y2)`.
- `sequence` child `transition={{type: "dissolve"|"slideFromRight"|"slideFromLeft"|"fadeToBlack"|"fadeToWhite", duration: 0.5}}`.

## HyperFrames overlays

`edit_project {operation: add_hyperframes_overlay, params: {template_path,
position_sec, duration_sec, variables}}`. The template is an HTML **fragment**
in a file inside the project (e.g. `graphics/title.html`); write it with your
file tools first. Open Edit mounts it as its own nested composition at
`position_sec`, so do **not** add `<html>`, a root `data-composition-id`, or
`data-start` on the fragment itself.

- `{{name}}` placeholders take primitive `variables` (HTML-escaped). Lists or
  objects arrive as `window.__open_edit_vars_<composition id>`.
- Reserved placeholders: `{{composition_id}}`, `{{start_sec}}`, `{{duration_sec}}`.
- **Animation must be a GSAP timeline registered under the composition id**;
  that is what makes t=0 the overlay start and keeps frames deterministic:

```html
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<div id="lt" style="position:absolute;left:80px;bottom:80px;opacity:0">{{title}}</div>
<script>
  window.__timelines = window.__timelines || {};
  const tl = gsap.timeline({ paused: true });
  tl.to("#lt", { opacity: 1, y: -10, duration: 0.6, ease: "power3.out" }, 0);
  window.__timelines["{{composition_id}}"] = tl;
</script>
```

- CSS `@keyframes` and WAAPI run on **timeline** time, not overlay time: at
  `position_sec > 0` they have already finished. Use GSAP, or add
  `animation-delay: {{start_sec}}s`. Never use `Date.now`, `setTimeout` or
  `requestAnimationFrame` loops.
- Static overlays need no script.
- The `add_hyperframes_overlay` result includes `lint` (HyperFrames' own
  checks with `fixHint`). Fix every error before rendering.
- Starter templates ship at `open_edit/render/templates/overlay/`
  (`lower_third.html`, `caption_card.html`); copy one into the project and edit it.
- More engine detail: `npx hyperframes docs gsap|data-attributes|troubleshooting`,
  not the minified `dist/*.js`.

## Remotion migration

Existing `add_remotion_composition` ops still render (needs `open_edit setup
legacy-remotion`). To migrate one, rebuild it in Diffusion (or a GSAP overlay)
with the same timing, track and alpha, compare representative frames from a
proxy render, and only then remove the legacy op. Never create new Remotion ops.
