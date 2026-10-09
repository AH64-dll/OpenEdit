"""Drafts belong to the forms an inspector actually repopulates."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest


def test_scoped_inspector_refresh_preserves_child_drafts_and_external_changes():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node not installed')
    module = Path('open_edit/serve/static/js/dom.js').resolve().as_uri()
    script = r'''
const { keepDrafts } = await import(MODULE);
const assert = (await import('node:assert/strict')).default;
globalThis.document = {activeElement: null};
const field = value => ({name:'value',type:'text',value,dataset:{},disabled:false,
  focus() { document.activeElement = this; },
  setSelectionRange(start,end) { this.selectionStart=start;this.selectionEnd=end; }});
const layer = {dataset:{draftKey:'layer:title'},elements:[field('100')]};
const animation = {dataset:{draftKey:'keyframe:motion:first'},elements:[field('10')]};
const child = {querySelectorAll:() => [animation]};
const parent = {querySelectorAll:selector => selector.startsWith(':scope >') ? [layer] : [layer,animation]};
keepDrafts(child, () => {});
animation.elements[0].value = '99';
animation.elements[0].selectionStart=1;animation.elements[0].selectionEnd=2;
document.activeElement=animation.elements[0];
keepDrafts(parent, () => { layer.elements[0].value='100'; }, ':scope > form[data-draft-key]');
keepDrafts(child, () => { animation.elements=[field('10')]; });
assert.equal(animation.elements[0].value,'99');
assert.equal(animation.elements[0].dataset.draftInitial,'10');
assert.equal(document.activeElement,animation.elements[0]);
assert.equal(animation.elements[0].selectionStart,1);
assert.equal(animation.elements[0].selectionEnd,2);
// A genuinely changed saved value takes priority over the old local draft.
keepDrafts(child, () => { animation.elements=[field('12')]; });
assert.equal(animation.elements[0].value,'12');
assert.equal(animation.elements[0].dataset.draftInitial,'12');
// Checkbox drafts retain their checked state, rather than the input value.
animation.elements=[{name:'enabled',type:'checkbox',checked:false,dataset:{},disabled:false}];
document.activeElement=null;
keepDrafts(child, () => {});
animation.elements[0].checked=true;
keepDrafts(child, () => { animation.elements=[{name:'enabled',type:'checkbox',checked:false,dataset:{},disabled:false}]; });
assert.equal(animation.elements[0].checked,true);
'''.replace('MODULE', json.dumps(module))
    result = subprocess.run([node, '--input-type=module', '-e', script], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
