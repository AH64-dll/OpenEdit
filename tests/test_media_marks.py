"""Video annotations stay out of the timeline until explicitly converted."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from open_edit.integrations.diffusion.graphics import graphics_ready, inspect_source
from open_edit.kernel.export_service import project_timeline
from open_edit.kernel.studio_service import commit_studio, get_editing_context, get_studio
from open_edit.storage.edit_graph import EditGraphStore


def test_marks_and_converted_graphics_are_independent_durable_sources(tmp_path):
    if not shutil.which('node') or not graphics_ready():
        pytest.skip('Optional graphics compiler is required')
    module = Path('open_edit/serve/static/js/mark-graphics.js').resolve().as_uri()
    script = '''
const {markGraphic}=await import(MODULE);
const tools=['rectangle','arrow','freehand','note','pin'];
console.log(JSON.stringify(tools.map((tool,i)=>markGraphic({tool,color:'#ffcc55',anchor_sec:4,text:'literal <tag> {code} "quotes"'},[[10,20],[60,90]],3840,2160,2,30,'graphic'+i))));
'''.replace('MODULE', json.dumps(module))
    values = json.loads(subprocess.check_output(['node', '--input-type=module', '-e', script], text=True))
    for data in values:
        doc = inspect_source(data['source'])
        assert doc['scene']['width'] == 1920 and doc['scene']['height'] == 1080
        assert doc['elements'][-1]['text'] == 'literal <tag> {code} "quotes"'
    store = EditGraphStore(tmp_path / '.open_edit/edit_graph.db')
    mark = {'tool': 'arrow', 'points': [[10, 20], [60, 90]], 'anchor_sec': 4,
            'end_sec': 6, 'scope': 'range', 'target_ids': [], 'text': 'Align here'}
    commit_studio(tmp_path, expected_revision=0, changes=[{'kind': 'annotation', 'object_id': 'mark', 'data': mark}])
    assert not project_timeline(tmp_path).tracks
    assert get_editing_context(tmp_path, annotation_ids=['mark'])['annotations'][0]['data']['text'] == 'Align here'
    commit_studio(tmp_path, expected_revision=store.graph_revision(), changes=[{'kind': 'document', 'object_id': 'converted', 'data': values[1]}])
    assert project_timeline(tmp_path).tracks[0].clips[0].position_sec == 4
    commit_studio(tmp_path, expected_revision=store.graph_revision(), changes=[{'kind': 'annotation', 'object_id': 'mark', 'data': None}])
    assert project_timeline(tmp_path).tracks[0].clips[0].document_id == 'converted'
    store.history_step('undo', store.graph_revision())
    store.history_step('undo', store.graph_revision())
    assert not project_timeline(tmp_path).tracks
    assert get_studio(tmp_path)['objects'][0]['object_id'] == 'mark'
