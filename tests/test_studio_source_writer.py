"""Real source compiler tests for editable composition structure and literal text."""
import json
import shutil
import subprocess

import pytest

from open_edit.integrations.diffusion.graphics import (
    DEFAULT_SOURCE,
    browser_directory,
    graphics_ready,
)


@pytest.fixture
def rewrite():
    if not graphics_ready():
        pytest.skip('Optional graphics source compiler is not installed')
    def call(source, edits):
        code = '''const fs = require('node:fs');
const { rewrite, parse, compile } = require('./compile.cjs');
const request = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
 const source = await rewrite(request.source, request.edits);
 await compile(source);
 process.stdout.write(JSON.stringify({ source, document: parse(source) }));
})().catch(error => { process.stderr.write(error.message); process.exitCode = 1; });'''
        proc = subprocess.run([shutil.which('node'), '-e', code], input=json.dumps({'source': source, 'edits': edits}),
                              text=True, capture_output=True, cwd=browser_directory(), timeout=30)
        if proc.returncode:
            raise ValueError(proc.stderr)
        return json.loads(proc.stdout)
    return call


def test_property_and_text_edits_preserve_comments_and_stable_ids(rewrite):
    source = DEFAULT_SOURCE.replace('return <stage', '// Keep this creative direction\n  return <stage')
    result = rewrite(source, [
        {'kind': 'set', 'source': 'index.tsx:title', 'props': {'x': 144, 'rotation': 15, 'fontSize': 60}},
        {'kind': 'text', 'source': 'index.tsx:title', 'text': 'Hello <world> & {you} — أهلاً'},
    ])
    assert 'Keep this creative direction' in result['source']
    title = next(e for e in result['document']['elements'] if e['id'] == 'title')
    assert title['x'] == 144 and title['rotation'] == 15 and title['fontSize'] == 60
    assert title['text'] == 'Hello <world> & {you} — أهلاً'


def test_insert_group_duplicate_move_and_delete_are_source_edits(rewrite):
    result = rewrite(DEFAULT_SOURCE, [
        {'kind': 'group', 'sources': ['index.tsx:panel', 'index.tsx:title'], 'id': 'lower-third'},
        {'kind': 'duplicate', 'source': 'index.tsx:lower-third', 'id_map': {
            'lower-third': 'copy-group', 'panel': 'copy-panel', 'title': 'copy-title'}},
        {'kind': 'text', 'source': 'index.tsx:copy-title', 'text': 'Second title'},
        {'kind': 'move', 'source': 'index.tsx:copy-title', 'parent': 'index.tsx:graphics-scene', 'before': 'index.tsx:lower-third'},
        {'kind': 'remove', 'source': 'index.tsx:copy-group'},
        {'kind': 'insert', 'parent': 'index.tsx:lower-third', 'jsx': '<rect id="accent" width={12} height={24} fill="#ff0000" />'},
    ])
    elements = {e['id']: e for e in result['document']['elements']}
    assert elements['title']['parent_id'] == 'lower-third'
    assert elements['copy-title']['parent_id'] == 'graphics-scene'
    assert elements['copy-title']['text'] == 'Second title'
    assert 'copy-group' not in elements and 'copy-panel' not in elements
    assert elements['accent']['parent_id'] == 'lower-third'


@pytest.mark.parametrize('edit', [
    {'kind': 'set', 'source': 'index.tsx:title', 'props': {'id': 'renamed'}},
    {'kind': 'set', 'source': 'index.tsx:title', 'props': {'onClick': 'evil'}},
    {'kind': 'remove', 'source': 'index.tsx:graphics-scene'},
    {'kind': 'remove', 'source': 'index.tsx:graphics-stage'},
    {'kind': 'insert', 'parent': 'index.tsx:graphics-scene', 'jsx': '<rect id="bad" x={process.exit()} />'},
    {'kind': 'move', 'source': 'index.tsx:panel', 'parent': 'index.tsx:panel'},
    {'kind': 'duplicate', 'source': 'index.tsx:title', 'id_map': {'title': 'panel'}},
])
def test_invalid_structural_edits_never_produce_accepted_source(rewrite, edit):
    with pytest.raises(ValueError):
        rewrite(DEFAULT_SOURCE, [edit])


def test_unchanged_source_is_byte_identical(rewrite):
    assert rewrite(DEFAULT_SOURCE, [])['source'] == DEFAULT_SOURCE


def test_translation_shifts_keyframes_without_erasing_animation(rewrite):
    source = DEFAULT_SOURCE.replace('Your title</text>', '''Your title
      <keyframeTrack id="title-motion" property="x">
        <keyframe id="motion-in" time={0} value={100} easing="easeIn" />
        <keyframe id="motion-out" time={2} value={300} easing="easeOut" />
      </keyframeTrack></text>''')
    result = rewrite(source, [{'kind': 'translate', 'source': 'index.tsx:title', 'dx': -25, 'dy': 10}])
    elements = {e['id']: e for e in result['document']['elements']}
    assert elements['title']['x'] == 75 and elements['title']['y'] == 370
    assert elements['motion-in']['value'] == 75 and elements['motion-out']['value'] == 275
    assert elements['motion-in']['easing'] == 'easeIn' and elements['motion-out']['time'] == 2
