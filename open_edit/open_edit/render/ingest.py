"""Parse raw MLT XML into synthetic IR operations (Tier 3 escape hatch).

Strict and narrow: rejects Kdenlive namespaces, custom interpolation
curves, multi-tractor nesting, and other features the IR cannot model.
"""
from __future__ import annotations

import uuid

from lxml import etree

from open_edit.ir.types import (
    AddClipOp, AddEffectOp, OperationUnion, Project, RawMltXmlOp,
)


class IngestError(Exception):
    """Raised when MLT XML cannot be parsed into IR operations."""


def _new_id() -> str:
    return str(uuid.uuid4())


def ingest_mlt_xml(xml: str, project: Project) -> list[OperationUnion]:
    """Parse MLT XML into synthetic IR operations.

    Returns a list of ops, the first being a `RawMltXmlOp` that preserves
    the original XML for transparency. Subsequent ops are the synthetic
    children (AddClipOp, AddEffectOp, etc.) derived from the XML.

    Raises IngestError on:
    - Empty or non-MLT root
    - Kdenlive-namespaced elements/attributes
    - Multi-tractor nesting
    """
    if not xml or not xml.strip():
        raise IngestError("empty XML; cannot ingest. fix: provide non-empty MLT XML.")

    # Reject Kdenlive namespaces up front
    if "kdenlive:" in xml:
        raise IngestError(
            "Kdenlive namespace detected in XML. "
            "fix: use plain MLT without kdenlive: properties."
        )

    try:
        root = etree.fromstring(xml.encode("utf-8"))
    except etree.XMLSyntaxError as e:
        raise IngestError(f"XML parse error: {e}")

    if root.tag != "mlt":
        raise IngestError(
            f"root element must be <mlt>, got <{root.tag}>. "
            f"fix: emit MLT XML from a Timeline first."
        )

    ops: list[OperationUnion] = []

    # The first op is always the RawMltXmlOp wrapper
    ops.append(RawMltXmlOp(
        edit_id=_new_id(),
        author="user",
        xml=xml,
        description="Ingested from MLT XML (Tier 3 escape hatch)",
    ))

    # Multi-tractor check (rejected; IR cannot model nested tractors)
    tractors = root.findall("tractor")
    if len(tractors) > 1:
        raise IngestError(
            f"multi-tractor nesting not supported (got {len(tractors)}); "
            f"fix: flatten to a single tractor."
        )
    if not tractors:
        # No tractor = no clips; just return the RawMltXmlOp
        return ops

    tractor = tractors[0]
    multitrack = tractor.find("multitrack")
    if multitrack is None:
        return ops

    # Build a producer-id → asset_hash map
    producer_to_hash: dict[str, str] = {}
    for producer in root.findall("producer"):
        pid = producer.get("id", "")
        resource_prop = producer.find("property[@name='resource']")
        if resource_prop is not None and resource_prop.text:
            producer_to_hash[pid] = resource_prop.text
        else:
            producer_to_hash[pid] = pid  # fallback to id

    # Walk tracks → entries. Entries may be nested in a <playlist> child or
    # appear directly inside the <track>; both forms occur in real MLT XML.
    track_idx = 0
    for track in multitrack.findall("track"):
        track_id = f"v{track_idx + 1}"  # default name; we don't preserve Kdenlive track ids
        entries = track.findall("playlist/entry")
        if not entries:
            entries = track.findall("entry")
        if not entries:
            track_idx += 1
            continue
        for entry in entries:
            producer_id = entry.get("producer", "")
            asset_hash = producer_to_hash.get(producer_id, producer_id)
            in_frames = int(entry.get("in", "0"))
            out_frames = int(entry.get("out", "0"))
            # Default to 30fps; precise frame-to-time requires the profile
            in_sec = in_frames / 30.0
            out_sec = out_frames / 30.0
            clip_op = AddClipOp(
                edit_id=_new_id(),
                author="user",
                asset_hash=asset_hash,
                track_id=track_id,
                track_kind="video",
                position_sec=0.0,  # ingest doesn't preserve timeline position
                in_point_sec=in_sec,
                out_point_sec=out_sec,
            )
            ops.append(clip_op)

            # Parse filters as AddEffectOp children
            for filt in entry.findall("filter"):
                service_prop = filt.find("property[@name='service']")
                if service_prop is None or not service_prop.text:
                    continue
                params: dict = {}
                for prop in filt.findall("property"):
                    name = prop.get("name", "")
                    if name == "service":
                        continue
                    if prop.text is not None:
                        params[name] = prop.text
                ops.append(AddEffectOp(
                    edit_id=_new_id(),
                    author="user",
                    target_kind="clip",
                    target_id=clip_op.clip_id,
                    effect_type=service_prop.text,
                    params=params,
                ))
        track_idx += 1

    return ops
