"""Validation of operations against a project's current state.

Returns a list of error messages (empty list = valid). Each error
includes a `fix:` line per the spec.
"""
from __future__ import annotations

import itertools
from pathlib import Path
from typing import TYPE_CHECKING

from open_edit.ir.types import (
    AddClipOp,
    AddEffectOp,
    AddRemotionCompositionOp,
    AddTransitionOp,
    ChangeClipSpeedOp,
    ControlEffectOp,
    DuplicateClipOp,
    GroupEditsOp,
    MoveClipOp,
    NormalizeAudioOp,
    OperationUnion,
    Project,
    RemoveClipOp,
    RemoveEffectOp,
    RemoveGraphicsSourceOp,
    RemoveKeyframeOp,
    RemoveRemotionCompositionOp,
    RemoveTransitionOp,
    ReplaceClipSourceOp,
    RippleDeleteClipOp,
    SetAudioGainOp,
    SetClipSpeedRampOp,
    SetEffectParamOp,
    SetGraphicsSourceOp,
    SetKeyframeOp,
    SetTransitionPropertyOp,
    SlipClipOp,
    SplitClipOp,
    Timeline,
    TrimClipOp,
    UngroupEditsOp,
)

if TYPE_CHECKING:
    from open_edit.ir.catalog.loader import EffectCatalog


_DEFAULT_CATALOG: EffectCatalog | None = None


def _get_default_catalog() -> EffectCatalog:
    """Load the bundled effect catalog once, on first use, and cache it."""
    global _DEFAULT_CATALOG
    if _DEFAULT_CATALOG is None:
        from open_edit.ir.catalog.loader import EffectCatalog
        catalog_dir = Path(__file__).parent / "catalog"
        _DEFAULT_CATALOG = EffectCatalog(catalog_dir)
    return _DEFAULT_CATALOG


def _known_clip_ids(project: Project) -> set[str]:
    return _known_ids_from_ops(project.edit_graph)[0]


def _known_effect_ids(project: Project) -> set[str]:
    return _known_ids_from_ops(project.edit_graph)[1]


def validate_op(
    op: OperationUnion,
    project: Project,
    catalog: EffectCatalog | None = None,
) -> list[str]:
    """Validate an operation against the project. Returns a list of errors.

    The default catalog is loaded from the bundled effects directory on
    first use. Tests can pass an explicit ``catalog=`` to isolate from the
    real catalog. Spec §6.1.1 requires the unknown-effect-type check to
    be unconditional, so the catalog is always applied when one is
    available.
    """
    if catalog is None:
        catalog = _get_default_catalog()
    errors: list[str] = []

    if op.status != "applied":
        return errors

    if isinstance(op, AddClipOp):
        if op.asset_hash not in project.assets:
            errors.append(
                f"Unknown asset_hash '{op.asset_hash}'. "
                f"fix: import the asset first via AssetStore.ingest()."
            )
        if op.position_sec < 0:
            errors.append(
                f"position_sec must be >= 0; got {op.position_sec}. "
                f"fix: use a non-negative position."
            )
        if op.in_point_sec < 0:
            errors.append(
                f"in_point_sec must be >= 0; got {op.in_point_sec}. "
                f"fix: use a non-negative in-point."
            )
        if op.out_point_sec is not None and op.out_point_sec <= op.in_point_sec:
            errors.append(
                f"out_point_sec ({op.out_point_sec}) must be greater than "
                f"in_point_sec ({op.in_point_sec}). "
                f"fix: set out_point_sec > in_point_sec, or leave as None."
            )

    elif isinstance(op, RemoveClipOp):
        pass  # no-op if unknown

    elif isinstance(op, MoveClipOp):
        if op.clip_id not in _known_clip_ids(project):
            errors.append(
                f"MoveClipOp: clip_id '{op.clip_id}' not found in project. "
                f"fix: ensure the clip was added before moving it."
            )

    elif isinstance(op, TrimClipOp):
        if op.clip_id not in _known_clip_ids(project):
            errors.append(
                f"TrimClipOp: clip_id '{op.clip_id}' not found in project. "
                f"fix: ensure the clip was added before trimming it."
            )
        if op.new_in_point_sec >= op.new_out_point_sec:
            errors.append(
                f"new_in_point_sec ({op.new_in_point_sec}) must be less than "
                f"new_out_point_sec ({op.new_out_point_sec}). "
                f"fix: ensure in < out."
            )

    elif isinstance(op, AddTransitionOp):
        if op.clip_a_id not in _known_clip_ids(project):
            errors.append(
                f"AddTransitionOp: clip_a_id '{op.clip_a_id}' not found. "
                f"fix: ensure clip_a is added before the transition."
            )
        if op.clip_b_id not in _known_clip_ids(project):
            errors.append(
                f"AddTransitionOp: clip_b_id '{op.clip_b_id}' not found. "
                f"fix: ensure clip_b is added before the transition."
            )
        if op.duration_sec <= 0:
            errors.append(
                f"duration_sec must be > 0; got {op.duration_sec}. "
                f"fix: set a positive duration."
            )

    elif isinstance(op, AddEffectOp):
        if catalog is not None and not catalog.is_known(op.effect_type):
            known = ", ".join(sorted(catalog.known_names()))
            errors.append(
                f"AddEffectOp: effect_type '{op.effect_type}' is not in the catalog. "
                f"fix: use one of: {known}."
            )
        if op.target_kind == "clip" and op.target_id not in _known_clip_ids(project):
            errors.append(
                f"AddEffectOp: target clip '{op.target_id}' not found. "
                f"fix: add the clip before applying the effect."
            )
        if catalog is not None:
            spec = catalog.get(op.effect_type)
            if spec is not None and op.target_kind not in spec.target_kind:
                allowed = ", ".join(spec.target_kind)
                errors.append(
                    f"AddEffectOp: effect '{op.effect_type}' cannot be "
                    f"applied to {op.target_kind}; it supports: {allowed}. "
                    f"fix: change target_kind to one of: {allowed}."
                )

    elif isinstance(op, SetKeyframeOp):
        if op.effect_id not in _known_effect_ids(project):
            errors.append(
                f"SetKeyframeOp: effect_id '{op.effect_id}' not found. "
                f"fix: add the effect before setting keyframes."
            )

    elif isinstance(op, SetAudioGainOp):
        if op.clip_id not in _known_clip_ids(project):
            errors.append(
                f"SetAudioGainOp: clip_id '{op.clip_id}' not found. "
                f"fix: add the audio clip before setting gain."
            )

    return errors


class OpValidationError(ValueError):
    """Raised by EditGraphStore.append when an op fails validation."""


class TimelineValidationError(ValueError):
    """Raised by derive_timeline(strict=True) when the timeline is broken."""


def validate_timeline(timeline: Timeline) -> list[str]:
    """Return timeline-level errors (empty list = valid).

    Detects overlapping clips on the same track and non-positive clip
    durations. Transitions do not create overlaps in the derived timeline
    (they trim clip boundaries to meet at the cut), so a plain interval
    check is correct.
    """
    errors: list[str] = []
    eps = 1e-6
    for track in timeline.tracks:
        clips = sorted(track.clips, key=lambda c: c.position_sec)
        for prev, cur in itertools.pairwise(clips):
            prev_end = prev.position_sec + (prev.out_point_sec - prev.in_point_sec)
            if prev_end > cur.position_sec + eps:
                hint = (
                    " To layer sounds (music + SFX), place each layer on its "
                    "own audio track (a1, a2, ...)."
                    if track.kind == "audio"
                    else ""
                )
                errors.append(
                    f"Overlap on track {track.track_id}: clip {prev.clip_id!r} "
                    f"spans [{prev.position_sec:.3f}, {prev_end:.3f}] but clip "
                    f"{cur.clip_id!r} starts at {cur.position_sec:.3f}.{hint}"
                )
        for c in track.clips:
            dur = c.out_point_sec - c.in_point_sec
            if dur <= 0:
                errors.append(
                    f"Clip {c.clip_id!r} has non-positive duration ({dur:.3f}s)."
                )
    return errors


def _known_ids_from_ops(ops) -> tuple[set[str], set[str]]:
    """Clip/effect ids that exist after replaying ``ops`` (tolerant).

    Mirrors the clip/effect creation and per-clip effect-list mutations done
    by ``apply_operation`` — including split / ripple / duplicate copies,
    speed-ramp / normalize / speed effects and index-addressed removals —
    so reference checks recognise derived identities. Per-clip effect state
    is an ordered list of ``(effect_id, effect_type)`` entries replayed in
    apply order (AddEffectOp appends, RemoveEffectOp pops the entry at
    ``op.effect_index``, speed/ramp upsert the first same-type entry or mint
    ``op.edit_id``), so an index-addressed removal removes the effect that
    apply actually removes. It does NOT run the full timeline math and never
    raises, so a semantically-invalid *prior* op (e.g. an oversized
    transition) does not block appending an unrelated, valid op.

    Transition effects appended by ``AddTransitionOp`` occupying a
    clip's ``effects`` list are included as identity/type entries so an
    index removal at that position is faithful; ``ControlEffectOp
    action='remove'`` ("Use the transition controls") and
    ``RemoveTransitionOp`` drop the matched transition entry the same way
    ``_apply_remove_transition`` matches effect ids.
    """
    clips: set[str] = set()
    effects: set[str] = set()
    documents: dict[str, set[str]] = {}
    clip_effects: dict[str, list[tuple[str, str]]] = {}
    transition_targets: dict[str, str] = {}

    def register(clip_id: str, effect_id: str, effect_type: str, clip_b_id=None) -> None:
        effects.add(effect_id)
        clip_effects.setdefault(clip_id, []).append((effect_id, effect_type))
        if isinstance(clip_b_id, str):
            transition_targets[effect_id] = clip_b_id
        else:
            transition_targets.pop(effect_id, None)

    for op in ops:
        if op.status != "applied":
            continue
        if isinstance(op, AddClipOp):
            clips.add(op.clip_id)
        elif isinstance(op, SetGraphicsSourceOp):
            if op.document_id not in documents:
                documents[op.document_id] = {op.clip_id}
                clips.add(op.clip_id)
        elif isinstance(op, RemoveGraphicsSourceOp):
            clips.difference_update(documents.pop(op.document_id, set()))
        elif isinstance(op, RemoveClipOp):
            clips.discard(op.clip_id)
            for _effect_id, _ in clip_effects.pop(op.clip_id, []):
                effects.discard(_effect_id)
        elif isinstance(op, DuplicateClipOp):
            originals = clip_effects.get(op.clip_id, [])
            if op.clip_id not in clips or set(op.effect_ids) != {eid for eid, _ in originals}:
                continue
            clips.add(op.new_clip_id)
            copies: list[tuple[str, str]] = []
            for original_id, original_type in originals:
                new_id = op.effect_ids.get(original_id)
                if new_id:
                    copies.append((new_id, original_type))
                    if original_id in transition_targets:
                        transition_targets[new_id] = transition_targets[original_id]
            clip_effects[op.new_clip_id] = copies
            effects.update(id for id, _ in copies)
            for instances in documents.values():
                if op.clip_id in instances:
                    instances.add(op.new_clip_id)
        elif isinstance(op, SplitClipOp):
            from uuid import NAMESPACE_URL, uuid5

            copied: list[tuple[str, str]] = clip_effects.pop(op.clip_id, [])
            left_copies: list[tuple[str, str]] = []
            right_copies: list[tuple[str, str]] = []
            for original_id, original_type in copied:
                left_copies.append((original_id, original_type))
                minted = str(uuid5(NAMESPACE_URL, f'openedit:split:{op.right_clip_id}:{original_id}'))
                right_copies.append((minted, original_type))
                if original_id in transition_targets:
                    transition_targets[minted] = transition_targets[original_id]
            clip_effects[op.left_clip_id] = left_copies
            clip_effects[op.right_clip_id] = right_copies
            for minted, _ in right_copies:
                effects.add(minted)
            clips.discard(op.clip_id)
            clips.add(op.left_clip_id)
            clips.add(op.right_clip_id)
            for instances in documents.values():
                if op.clip_id in instances:
                    instances.discard(op.clip_id)
                    instances.update((op.left_clip_id, op.right_clip_id))
        elif isinstance(op, RippleDeleteClipOp):
            clips.discard(op.clip_id)
            for _effect_id, _ in clip_effects.pop(op.clip_id, []):
                effects.discard(_effect_id)
        elif isinstance(op, AddTransitionOp):
            # _apply_add_transition appends the transition effect to clip_a's
            # effects list (id 'transition_{edit_id}'), so a later
            # index-addressed RemoveEffectOp at that position must remove it.
            if op.clip_a_id in clips and op.clip_b_id in clips:
                register(op.clip_a_id, f'transition_{op.edit_id}', f'transition_{op.transition_type}', op.clip_b_id)
        elif isinstance(op, AddEffectOp):
            if op.target_kind == 'clip':
                if op.target_id in clips:
                    register(op.target_id, op.effect_id, op.effect_type, op.params.get('clip_b_id'))
            else:
                effects.add(op.effect_id)
        elif isinstance(op, ControlEffectOp):
            if op.target_kind == 'clip':
                entries = clip_effects.get(op.target_id, [])
                index = next((i for i, entry in enumerate(entries) if entry[0] == op.effect_id), None)
                if index is None or entries[index][1].startswith('transition_'):
                    continue
                if op.action == 'move' and op.index is not None and op.index < len(entries):
                    entries.insert(op.index, entries.pop(index))
                elif op.action == 'duplicate' and op.new_effect_id and op.new_effect_id not in effects:
                    entries.insert(index + 1, (op.new_effect_id, entries[index][1]))
                    effects.add(op.new_effect_id)
                    if op.effect_id in transition_targets:
                        transition_targets[op.new_effect_id] = transition_targets[op.effect_id]
                elif op.action == 'remove':
                    entries.pop(index)
                    effects.discard(op.effect_id)
                elif op.action == 'reset':
                    transition_targets.pop(op.effect_id, None)
            elif op.action == 'duplicate' and op.new_effect_id:
                effects.add(op.new_effect_id)
            elif op.action == 'remove':
                effects.discard(op.effect_id)
        elif isinstance(op, RemoveEffectOp):
            entries = clip_effects.get(op.clip_id)
            if entries is not None and 0 <= op.effect_index < len(entries):
                dropped = entries.pop(op.effect_index)
                effects.discard(dropped[0])
        elif isinstance(op, RemoveTransitionOp):
            # _apply_remove_transition drops the matched effect from every
            # clip's effects list; mirror that for known per-clip entries.
            def matches(entry: tuple[str, str], transition_id: str = op.transition_id) -> bool:
                return (
                    entry[0] == transition_id or entry[0] == f"transition_{transition_id}"
                    or transition_targets.get(entry[0]) == transition_id
                )
            for clip_id, entries in list(clip_effects.items()):
                kept = [entry for entry in entries if not matches(entry)]
                for entry in list(clip_effects.get(clip_id, [])):
                    if matches(entry) and len(kept) < len(entries):
                        effects.discard(entry[0])
                clip_effects[clip_id] = kept
        elif isinstance(op, SetEffectParamOp) and op.param_name == 'clip_b_id':
            entries = clip_effects.get(op.clip_id, [])
            matched = next((entry for entry in entries if entry[0] == op.effect_id), None) if op.effect_id else (
                entries[op.effect_index] if 0 <= op.effect_index < len(entries) else None
            )
            if matched:
                transition_targets[matched[0]] = op.value
        elif isinstance(op, SetTransitionPropertyOp) and op.prop_name == 'clip_b_id':
            for entries in clip_effects.values():
                for effect_id, _ in entries:
                    if effect_id in (op.transition_id, f'transition_{op.transition_id}') or transition_targets.get(effect_id) == op.transition_id:
                        transition_targets[effect_id] = op.value
        elif isinstance(op, ChangeClipSpeedOp):
            # _apply_change_clip_speed upserts the first 'speed' entry in
            # place (id preserved); only the first speed op on a clip mints
            # op.edit_id as a new effect.
            if op.clip_id not in clips:
                continue  # clip gone (removed/split away/duplicate-only source): apply would no-op
            entries = clip_effects.get(op.clip_id)
            if entries and any(t == 'speed' for _, t in entries):
                pass  # supersede: identity preserved, op.edit_id stays unregistered
            else:
                register(op.clip_id, op.edit_id, 'speed')
        elif isinstance(op, SetClipSpeedRampOp):
            if op.clip_id not in clips:
                continue
            entries = clip_effects.get(op.clip_id)
            if entries and any(t == 'speed_ramp' for _, t in entries):
                pass  # supersede: existing ramp id preserved
            else:
                register(op.clip_id, op.edit_id, 'speed_ramp')
        elif isinstance(op, NormalizeAudioOp):
            if op.target_kind == 'clip':
                if op.target_id in clips:
                    register(op.target_id, op.edit_id, 'volume')
            else:
                effects.add(op.edit_id)
        # ReplaceClipSourceOp / MoveClipOp / TrimClipOp / SlipClipOp keep ids
    return clips, effects


def _effects_for_clip(timeline, clip_id: str) -> list:
    """The effects attached to ``clip_id`` in a timeline ([] if unknown)."""
    for t in timeline.tracks:
        for c in t.clips:
            if c.clip_id == clip_id:
                return c.effects
    return []


def _timeline_ids(timeline) -> tuple[set[str], set[str], set[str]]:
    """Clip / effect / track ids present in a derived timeline.

    Unlike ``_known_ids_from_ops`` (a tolerant op-replay mirror), this is the
    actual derived state: effects created by ``AddTransitionOp`` (stored as
    ``transition_*`` effects on clip_a) are visible here, and clips that a
    chain of ops removed / split away are gone.
    """
    clip_ids: set[str] = set()
    effect_ids: set[str] = set()
    for t in timeline.tracks:
        for c in t.clips:
            clip_ids.add(c.clip_id)
            for e in c.effects:
                effect_ids.add(e.effect_id)
        for e in t.effects:
            effect_ids.add(e.effect_id)
    track_ids: set[str] = {t.track_id for t in timeline.tracks}
    return clip_ids, effect_ids, track_ids


def _validate_references_strict(op: OperationUnion, project: Project, timeline) -> list[str]:
    """Strict reference checks (script reference validation), returning error strings.

    This is the historical ``_validate_references`` from
    ``agent/script_runner/staging.py`` transcribed verbatim (raise -> error string):
    identity is timeline-derived (a batch op referencing a clip created
    earlier in the SAME batch passes because the caller passes the growing
    timeline), asset existence is enforced for ``AddClipOp`` /
    ``ReplaceClipSourceOp``, effects are index/param-checked, group labels
    come from the stored edit graph (not the working timeline), and every op
    must carry a non-None ``parent_id`` (the IR build path stamps it).
    """
    errors: list[str] = []
    asset_hashes = set(project.assets)
    track_ids = {t.track_id for t in timeline.tracks}
    clip_ids, effect_ids, _ = _timeline_ids(timeline)

    edit_ids: set[str] = set()
    group_labels: set[str] = set()
    for e in project.edit_graph:
        edit_ids.add(e.edit_id)
        if isinstance(e, GroupEditsOp):
            group_labels.add(e.label)

    # ---- clip-targeting ops (clip_id must exist) ----
    if isinstance(op, (
        TrimClipOp, MoveClipOp, RemoveClipOp,
        SlipClipOp, RippleDeleteClipOp, ChangeClipSpeedOp, SplitClipOp,
        SetClipSpeedRampOp, SetAudioGainOp,
    )) and op.clip_id not in clip_ids:
        errors.append(f"clip_id {op.clip_id!r} not in project")

    # ---- AddClipOp: asset must exist; track is auto-created ----
    if isinstance(op, AddClipOp) and op.asset_hash not in asset_hashes:
        errors.append(f"asset_hash {op.asset_hash!r} not in project")
        # AddClipOp auto-creates the track via _get_or_create_track, so we
        # do NOT pre-validate track_id here. The first op on a new track
        # would otherwise be rejected before the track is created.

    # ---- transitions ----
    if isinstance(op, AddTransitionOp):
        if op.clip_a_id not in clip_ids:
            errors.append(f"clip_a_id {op.clip_a_id!r} not in project")
        if op.clip_b_id not in clip_ids:
            errors.append(f"clip_b_id {op.clip_b_id!r} not in project")
    # Transitions are effects on clip_a and share the effect ID namespace.
    if isinstance(op, (RemoveTransitionOp, SetTransitionPropertyOp)) and op.transition_id not in effect_ids:
        errors.append(f"transition_id {op.transition_id!r} not in project")

    # ---- effects ----
    if isinstance(op, AddEffectOp):
        if op.target_kind == "clip":
            if op.target_id not in clip_ids:
                errors.append(f"target_id {op.target_id!r} not in project")
        elif op.target_kind == "track":
            if op.target_id not in track_ids:
                errors.append(f"target_id {op.target_id!r} not in project")
        else:
            errors.append(
                f"AddEffectOp.target_kind must be 'clip' or 'track', "
                f"got {op.target_kind!r}"
            )
    if isinstance(op, RemoveEffectOp):
        if op.clip_id not in clip_ids:
            errors.append(f"clip_id {op.clip_id!r} not in project")
        effects = _effects_for_clip(timeline, op.clip_id)
        if not (0 <= op.effect_index < len(effects)):
            errors.append(
                f"effect_index {op.effect_index} out of range for clip "
                f"{op.clip_id!r} (has {len(effects)} effects)"
            )
    if isinstance(op, SetEffectParamOp):
        if op.clip_id not in clip_ids:
            errors.append(f"clip_id {op.clip_id!r} not in project")
        effects = _effects_for_clip(timeline, op.clip_id)
        if not (0 <= op.effect_index < len(effects)):
            errors.append(
                f"effect_index {op.effect_index} out of range for clip "
                f"{op.clip_id!r} (has {len(effects)} effects)"
            )
        else:
            # Validate param_name exists in the effect's params dict.
            eff = effects[op.effect_index]
            if op.param_name not in eff.params:
                errors.append(
                    f"param_name {op.param_name!r} not in effect {eff.effect_id!r} "
                    f"(has params: {sorted(eff.params.keys())})"
                )

    # ---- keyframes ----
    if isinstance(op, SetKeyframeOp) and op.effect_id not in effect_ids:
        errors.append(f"effect_id {op.effect_id!r} not in project")
    if isinstance(op, RemoveKeyframeOp):
        if op.effect_id not in effect_ids:
            errors.append(f"effect_id {op.effect_id!r} not in project")
        # Look up the effect to check param + frame.
        target = None
        for t in timeline.tracks:
            for c in t.clips:
                for eff in c.effects:
                    if eff.effect_id == op.effect_id:
                        target = eff
                        break
                if target is not None:
                    break
            if target is not None:
                break
        if target is None:
            for t in timeline.tracks:
                for eff in t.effects:
                    if eff.effect_id == op.effect_id:
                        target = eff
                        break
                if target is not None:
                    break
        if target is not None and op.param not in target.keyframes:
            errors.append(
                f"param {op.param!r} not in effect {op.effect_id!r} "
                f"keyframes (has: {sorted(target.keyframes.keys())})"
            )

    # ---- source-replacement ----
    if isinstance(op, ReplaceClipSourceOp):
        if op.clip_id not in clip_ids:
            errors.append(f"clip_id {op.clip_id!r} not in project")
        if op.new_asset_hash not in asset_hashes:
            errors.append(f"asset_hash {op.new_asset_hash!r} not in project")

    # ---- audio normalize ----
    if isinstance(op, NormalizeAudioOp):
        if op.target_kind == "clip":
            if op.target_id not in clip_ids:
                errors.append(f"target_id {op.target_id!r} not in project")
        elif op.target_kind == "track":
            if op.target_id not in track_ids:
                errors.append(f"target_id {op.target_id!r} not in project")
        else:
            errors.append(
                f"NormalizeAudioOp.target_kind must be 'clip' or 'track', "
                f"got {op.target_kind!r}"
            )

    # ---- groups ----
    if isinstance(op, GroupEditsOp):
        for eid in op.edit_ids:
            if eid not in edit_ids:
                errors.append(f"edit_id {eid!r} not in project edit_graph")
    if isinstance(op, UngroupEditsOp) and op.label not in group_labels:
        errors.append(f"group label {op.label!r} not in project")

    # ---- RawMltXmlOp + FreeFormCodeOp: no reference check (free-form) ----

    if op.parent_id is None:
        errors.append("op has no parent_id (IR class should stamp at build time)")

    return errors


def validate_op_references(
    op: OperationUnion,
    project: Project,
    strict: bool = False,
    *,
    timeline=None,
) -> list[str]:
    """Reference-integrity check only (used at the append / vault door).

    Ensures a clip / transition / effect target actually exists in the
    current project. Identity is computed from the replayed ops (via
    ``_known_ids_from_ops``), not a raw Add-op scan, so clips produced by
    ``SplitClipOp`` and effects produced by speed-ramp / normalize ops are
    recognised — a ``split → trim the left half`` workflow must not be
    rejected. Deliberately does NOT check asset existence or effect-catalog
    membership — those are enforced by the script runner and at render time,
    so the agent stays free to operate. Returns a list of error strings
    (empty = valid).

    With ``strict=True`` the full strict reference check set runs instead
    (timeline-derived clip / effect / track identity, asset existence,
    transition-id, effect-index / param_name, group-label and parent-id
    checks; see ``_validate_references_strict``). ``timeline`` may be passed
    in so a batch of ops can be validated incrementally against the growing
    working timeline; when omitted it is derived from ``project``.
    """
    from open_edit.ir.studio_ops import STUDIO_OPERATIONS, references

    if isinstance(op, STUDIO_OPERATIONS):
        if timeline is None:
            from open_edit.ir.derive import derive_timeline

            timeline = derive_timeline(project)
        return references(op, timeline) + (["op has no parent_id"] if strict and op.parent_id is None else [])
    if strict:
        if timeline is None:
            from open_edit.ir.derive import derive_timeline
            timeline = derive_timeline(project)
        return _validate_references_strict(op, project, timeline)

    errors: list[str] = []
    known_clips, known_effects = _known_ids_from_ops(project.edit_graph)

    clip_targeting = (
        MoveClipOp, TrimClipOp, RemoveClipOp, SlipClipOp,
        RippleDeleteClipOp, ChangeClipSpeedOp, SplitClipOp,
        ReplaceClipSourceOp, SetClipSpeedRampOp, SetAudioGainOp,
    )
    if isinstance(op, clip_targeting) and op.clip_id not in known_clips:
        errors.append(
            f"{type(op).__name__}: clip_id {op.clip_id!r} not found in project."
        )

    if isinstance(op, AddTransitionOp):
        if op.clip_a_id not in known_clips:
            errors.append(
                f"AddTransitionOp: clip_a_id {op.clip_a_id!r} not found in project."
            )
        if op.clip_b_id not in known_clips:
            errors.append(
                f"AddTransitionOp: clip_b_id {op.clip_b_id!r} not found in project."
            )

    if isinstance(op, AddEffectOp) and op.target_kind == "clip" and op.target_id not in known_clips:
        errors.append(
            f"AddEffectOp: target clip {op.target_id!r} not found in project."
        )

    if isinstance(op, SetKeyframeOp) and op.effect_id not in known_effects:
        errors.append(
            f"SetKeyframeOp: effect_id {op.effect_id!r} not found in project."
        )

    return errors


def validate_op_for_append(op: OperationUnion, store) -> list[str]:
    """Validate one op's references against the store's current project state.

    Only reference integrity is enforced at the append (vault) door: a clip /
    transition / effect target must exist. Asset existence and effect-catalog
    membership are intentionally NOT enforced here. ``store`` is duck-typed
    (must expose ``load_all()``, ``db_path``, ``project_id``). No runtime
    import of EditGraphStore here to avoid a circular import.
    """
    errors: list[str] = []
    if isinstance(op, AddRemotionCompositionOp):
        if op.duration_sec <= 0:
            errors.append(
                f"duration_sec must be > 0; got {op.duration_sec}. "
                f"fix: set a positive Remotion composition duration."
            )
        if op.position_sec < 0:
            errors.append(
                f"position_sec must be >= 0; got {op.position_sec}. "
                f"fix: use a non-negative position."
            )
        ep = (op.entry_point or "").strip()
        if not ep or ep.startswith(("/", "\\")) or ".." in Path(ep).parts:
            errors.append(
                f"entry_point must be relative under .open_edit/remotion/; "
                f"got {op.entry_point!r}. "
                f"fix: use a path like 'src/index.ts'."
            )
        if not (op.composition_id or "").strip():
            errors.append(
                "composition_id is required. "
                "fix: pass the Remotion <Composition id>."
            )
    if isinstance(op, RemoveRemotionCompositionOp) and not (op.composition_uid or "").strip():
        errors.append(
            "composition_uid is required. "
            "fix: pass the uid returned by add_remotion_composition."
        )

    ops = store.load_all()
    project = Project(
        project_id=store.project_id,
        name=store.db_path.parent.name,
        workdir=store.db_path.parent,
        assets={},
        edit_graph=ops,
    )
    errors.extend(validate_op_references(op, project))
    return errors
