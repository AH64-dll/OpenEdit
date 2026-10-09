"""Nested/rotated hit regions and object-relative marks use composition space."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest


def test_geometry_under_rotated_scaled_parent_and_selection_ancestors():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node not installed')
    module = Path('open_edit/serve/static/js/studio-geometry.js').resolve().as_uri()
    code = '''
const { inverse, transformPoint, localDelta, insidePolygon, bounds, selectionRoots,
  layerLocked, annotationPoints, alignmentOffsets } = await import(MODULE);
const parent = {a:0,b:2,c:-2,d:0,e:100,f:50};
const local = [10,10], world = transformPoint(parent, local);
const corners = [[0,0],[40,0],[40,20],[0,20]].map(p=>transformPoint(parent,p));
const elements = [{id:'group',parent_id:'scene'},{id:'child',parent_id:'group'},{id:'other',parent_id:'scene'}];
process.stdout.write(JSON.stringify({world, roundtrip:transformPoint(inverse(parent),world),
  delta:localDelta(parent,20,10), inside:insidePolygon(world,corners), outside:insidePolygon([0,0],corners),
  roots:selectionRoots(['group','child','other'],elements), locked:layerLocked('child',elements,['group']),
  marks:annotationPoints({coordinate_space:'object',anchor_id:'child',points:[[10,20]]},[{id:'child',matrix:parent}]),
  missing:annotationPoints({coordinate_space:'object',anchor_id:'missing',points:[[10,20]]},[]),
  centered:alignmentOffsets([{id:'child',corners}], 'center', 960, 540),
  singular:inverse({a:0,b:0,c:0,d:0,e:0,f:0}), box:bounds(corners)}));
'''.replace('MODULE', json.dumps(module))
    result = subprocess.run([node, '--input-type=module', '-e', code], capture_output=True, text=True, timeout=10, check=True)
    data = json.loads(result.stdout)
    assert data['world'] == [80, 70] and data['roundtrip'] == [10, 10]
    assert data['delta'] == [5, -10]
    assert data['inside'] is True and data['outside'] is False
    assert data['roots'] == ['group', 'other'] and data['locked'] is True
    assert data['marks'] == [[60, 70]] and data['missing'] == []
    assert data['singular'] is None and data['centered']['child'] == [400, 0]
