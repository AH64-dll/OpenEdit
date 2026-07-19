"""Tests for the MLT XML ingest parser (Tier 3 escape hatch)."""
import pytest

from open_edit.ir.types import (
    AddClipOp, AddEffectOp, Project, RawMltXmlOp, OperationUnion,
)
from open_edit.render.ingest import ingest_mlt_xml, IngestError


def test_ingest_rejects_kdenlive_namespaces() -> None:
    xml = '<mlt><tractor><multitrack><track><kdenlive:producer/></track></multitrack></tractor></mlt>'
    with pytest.raises(IngestError, match="kdenlive"):
        ingest_mlt_xml(xml, Project(name="t"))


def test_ingest_rejects_empty_xml() -> None:
    with pytest.raises(IngestError, match="empty"):
        ingest_mlt_xml("", Project(name="t"))


def test_ingest_rejects_non_mlt_root() -> None:
    with pytest.raises(IngestError, match="<mlt"):
        ingest_mlt_xml("<not-mlt/>", Project(name="t"))


def test_ingest_parses_producer_and_entry() -> None:
    xml = '''<mlt>
        <producer id="p1">
          <property name="resource">abc.mp4</property>
        </producer>
        <tractor>
          <multitrack>
            <track>
              <entry producer="p1" in="0" out="60"/>
            </track>
          </multitrack>
        </tractor>
      </mlt>'''
    ops = ingest_mlt_xml(xml, Project(name="t"))
    add_clip_ops = [o for o in ops if isinstance(o, AddClipOp)]
    assert len(add_clip_ops) == 1
    assert add_clip_ops[0].asset_hash == "abc.mp4"
    assert add_clip_ops[0].track_id == "v1"


def test_ingest_returns_synthetic_raw_mlt_xml_op_at_front() -> None:
    """The ingest wraps the input as a RawMltXmlOp so the original XML is preserved."""
    xml = "<mlt><tractor><multitrack><track/></multitrack></tractor></mlt>"
    ops = ingest_mlt_xml(xml, Project(name="t"))
    # First op should be the synthetic RawMltXmlOp
    assert isinstance(ops[0], RawMltXmlOp)
    assert ops[0].xml == xml


def test_ingest_parses_filter_as_add_effect_op() -> None:
    xml = '''<mlt>
        <producer id="p1"><property name="resource">abc</property></producer>
        <tractor>
          <multitrack>
            <track>
              <entry producer="p1" in="0" out="60">
                <filter id="fx1">
                  <property name="service">volume</property>
                  <property name="gain">0.5</property>
                </filter>
              </entry>
            </track>
          </multitrack>
        </tractor>
      </mlt>'''
    ops = ingest_mlt_xml(xml, Project(name="t"))
    eff_ops = [o for o in ops if isinstance(o, AddEffectOp)]
    assert len(eff_ops) == 1
    assert eff_ops[0].effect_type == "volume"
    assert eff_ops[0].params["gain"] == "0.5"  # string form preserved
