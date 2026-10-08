"""Source animation controls preserve stable identity and use runtime curves."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from open_edit.integrations.diffusion.graphics import browser_directory, graphics_ready


def node(code, data=None):
    if not graphics_ready():
        pytest.skip('Optional graphics compiler is not installed')
    result = subprocess.run([shutil.which('node'), '--input-type=module', '-e', code],
                            input=json.dumps(data), capture_output=True, text=True,
                            cwd=browser_directory(), timeout=30)
    return result


SOURCE = '''export default function Graphics() { return <stage id="stage">
  <scene id="scene" width={320} height={180} active>
    {/* Keep this direction */}<rect id="box" x={10} width={60} height={40} end={2}/>
  </scene></stage>; }'''


def test_auto_key_inserts_initial_value_and_updates_existing_frame():
    module = Path('open_edit/serve/static/js/keyframes.js').resolve().as_uri()
    code = '''
import {createRequire} from 'node:module'; import fs from 'node:fs';
const require=createRequire(import.meta.url), {parse,compile,rewrite}=require('./compile.cjs');
const {keyframeEdits}=await import(MODULE);
let source=JSON.parse(fs.readFileSync(0,'utf8')), doc={...parse(source),fps:30,duration_sec:2};
const first=keyframeEdits(doc,'box','x',.51,80,'easeIn',10);
source=await rewrite(source,first);doc={...parse(source),fps:30,duration_sec:2};
const frames=doc.elements.filter(e=>e.tag==='keyframe'), oldIds=frames.map(e=>e.id);
source=await rewrite(source,keyframeEdits(doc,'box','x',.5,90,'cubicBezier(.4,0,.6,1)'));
await compile(source);
process.stdout.write(JSON.stringify({source,doc:parse(source),oldIds,first}));
'''.replace('MODULE', json.dumps(module))
    result = node(code, SOURCE)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    frames = [e for e in data['doc']['elements'] if e['tag']=='keyframe']
    assert [e['id'] for e in frames] == data['oldIds']
    assert [(e['time'],e['value']) for e in frames] == [(0,10),(.5,90)]
    assert frames[1]['easing'] == 'cubicBezier(.4,0,.6,1)'
    assert 'Keep this direction' in data['source']
    assert len([e for e in data['doc']['elements'] if e['tag']=='keyframeTrack']) == 1


@pytest.mark.parametrize('curve', ['linear','easeIn','easeOut','easeInOut','cubicBezier(0.1,-1,0.9,2)'])
def test_named_and_custom_curves_compile_without_rewriting_authored_source(curve):
    track = f'<keyframeTrack id="motion" property="x"><keyframe id="a" time={{0}} value={{0}} easing="{curve}"/><keyframe id="b" time={{1}} value={{80}}/></keyframeTrack>'
    source = SOURCE.replace('end={2}/>',f'end={{2}}>{track}</rect>')
    result = node('''import {createRequire} from 'node:module'; import fs from 'node:fs';
const {compile}=createRequire(import.meta.url)('./compile.cjs');
process.stdout.write(JSON.stringify(await compile(JSON.parse(fs.readFileSync(0,'utf8')))));''',source)
    assert result.returncode == 0, result.stderr
    assert next(e for e in json.loads(result.stdout)['document']['elements'] if e['id']=='a')['easing'] == curve


@pytest.mark.parametrize('track', [
    '<keyframeTrack id="t" property="x"><keyframe id="a" time={0} value={0} easing="unknown"/></keyframeTrack>',
    '<keyframeTrack id="t" property="x"><keyframe id="a" time={0} value={0} easing="cubicBezier(2,0,1,1)"/></keyframeTrack>',
    '<keyframeTrack id="t" property="x"><keyframe id="a" time={0} value={0}/><keyframe id="b" time={0} value={1}/></keyframeTrack>',
    '<keyframeTrack id="t" property="opacity"><keyframe id="a" time={0} value={2}/></keyframeTrack>',
    '<keyframeTrack id="t" property="color"><keyframe id="a" time={0} value={10}/></keyframeTrack>',
    '<keyframeTrack id="t" property="x"/><keyframeTrack id="u" property="x"/>',
])
def test_ambiguous_or_invalid_animation_is_rejected(track):
    source = SOURCE.replace('end={2}/>',f'end={{2}}>{track}</rect>')
    result = node('''import {createRequire} from 'node:module'; import fs from 'node:fs';
createRequire(import.meta.url)('./compile.cjs').parse(JSON.parse(fs.readFileSync(0,'utf8')));''',source)
    assert result.returncode != 0
