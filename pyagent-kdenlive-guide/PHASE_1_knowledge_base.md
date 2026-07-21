# Phase 1 — Knowledge Base (the "docs fed to the AI" part)

## Context (recap)

This is the direct answer to "I think we can get docs from the program and
feed it to the AI so it can know." Kdenlive already ships two structured,
machine-readable sources describing its own tools — we're not scraping prose
documentation, we're normalizing data that already exists in the right shape.
Depends on `spike-results/` from Phase 0.

## Goal

Produce one normalized catalog file PyAgent's system prompt / tool
definitions can be built from, covering every effect, transition, and (where
relevant) MLT-level filter Kdenlive can use — plus a short hand-written
cookbook for the handful of things that aren't documented anywhere (confirmed
gap: transition params like Wipe/Luma/Dissolve, per KDE bug #496494).

## Sources to ingest, in priority order

1. **Kdenlive's own effect/transition XML** — sparse-checkout or clone
   `github.com/KDE/kdenlive`, read `data/effects/*.xml`, `data/transitions/*.xml`,
   `data/generators/*.xml` if present. Read `data/effects/README.md` first —
   it documents the schema authoritatively (parameter types, `paramlist`,
   `paramlistdisplay`, dependency declarations, CDATA description blocks) —
   don't hand-guess the schema when the source explains it.
2. **MLT's YAML service metadata** — from `spike-results/mlt-yml-samples/`
   if Phase 0 found them locally, otherwise sparse-checkout
   `github.com/mltframework/mlt`, path `src/modules/*/*.yml`. Use this to
   fill in parameter detail for any `tag=` referenced by a Kdenlive effect
   XML that seems under-documented, and to surface MLT filters Kdenlive's UI
   doesn't expose but which are still legal to use in the XML directly.
3. **`src/kdenliveui.rc`** from the Kdenlive source — a standard KXMLGUI
   action/shortcut file. Not something PyAgent calls directly (there's no
   scripting surface it maps to in the file-based backend), but useful as a
   **vocabulary alignment** reference — action names here are what a human
   Kdenlive user calls things, and it's worth PyAgent using the same words.
   Also directly useful later if Phase 8's GUI-automation fallback ever needs
   real shortcut names.
4. **Hand-built cookbook** — for anything still unclear after 1–3 (transition
   params are the known example): in the Kdenlive GUI, make exactly one
   change, save, `git diff` (or plain `diff`) against the previous save.
   Repeat for: add a cut, add a crossfade/dissolve, add a title clip, add a
   marker, add a track, change project resolution, add a basic color-correct
   effect. Write each as a short "if you want X, the XML looks like Y" entry.
   Target 8–12 entries, not exhaustive — these are the highest-value patterns
   a real editing session actually needs.

## Output format

One catalog, structured for cheap lookup, e.g.:

```json
{
  "effects": [
    {
      "kdenlive_id": "crop",
      "mlt_service": "crop",
      "category": "effect",
      "name": "Edge Crop",
      "description": "Trim the edges of a clip",
      "parameters": [
        {"name": "top", "type": "constant", "min": 0, "max": "%maxHeight", "default": 0, "suffix": "pixels"}
      ],
      "source": "kdenlive-data/effects/crop.xml"
    }
  ],
  "transitions": [ ... ],
  "cookbook": [
    {"goal": "add a crossfade between two clips", "xml_pattern": "...", "notes": "..." }
  ]
}
```

Keep `source` on every entry — when PyAgent is wrong about a parameter, you
want to be able to trace it back to which file to fix, same principle as your
`edl.json` versioned-retry files preserving what went wrong.

## How PyAgent should actually consume this in v1

Don't build a vector-search/RAG pipeline for this yet — the whole catalog for
the effects and transitions Kdenlive ships is a few hundred KB at most, which
comfortably fits alongside the tool definitions in a system prompt, filtered
down to "the categories relevant to what the user just asked for" rather than
the entire catalog every turn (plain keyword/category filtering is enough:
if the user says "add a fade," you don't need the crop or subtitle-style
entries in context). Revisit this decision only if the catalog grows enough
that even a filtered slice is consistently blowing your context budget — a
concrete, checkable trigger, not a default architecture choice made up front.

## Explicit non-goals for this phase

- No embeddings/vector database yet — see above.
- Don't try to document every single MLT filter in existence — cover what
  Kdenlive's own `data/effects` + `data/transitions` expose, since that's the
  actual surface a human editor (and therefore PyAgent) would reach for.
- Don't hand-write cookbook entries for anything the structured XML/YAML
  already documents clearly — that's duplicated maintenance for no benefit.

## Acceptance criteria

- [ ] A single catalog file (JSON or equivalent) exists covering all of
      `data/effects/` and `data/transitions/`, each entry traceable to its
      source file.
- [ ] 8–12 cookbook entries exist for the patterns not otherwise well
      documented, each verified by an actual before/after diff of a real
      saved `.kdenlive` file — not written from memory or guesswork.
- [ ] A short `README.md` in this phase's output folder states where each
      source was pulled from (local install path, or which GitHub commit/ref
      it was cloned at) so the catalog can be regenerated later when Kdenlive
      updates.

## Handoff to Phase 2 / Phase 3

Phase 2's operation API (`apply_effect`, `add_transition`, etc.) should
validate its `name`/`id` arguments against this catalog rather than against a
hardcoded list. Phase 3's system-prompt builder pulls the filtered slice of
this catalog into context per turn.
