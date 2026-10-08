"""The safe optional installer must reproduce upstream's required runtime fix."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess

import pytest

from open_edit.integrations.diffusion.graphics import browser_directory, graphics_ready
from open_edit.integrations.diffusion.setup import apply_dependency_patches


def test_vendor_provenance_and_dependency_patch():
    root = browser_directory()
    provenance = json.loads((root / 'vendor/PROVENANCE.json').read_text())
    assert provenance['commit'] == 'fefcde9df7198466bd7cc9f3a9d7eae1575b5b12'
    for name, expected in provenance['sha256'].items():
        assert hashlib.sha256((root / 'vendor' / name).read_bytes()).hexdigest() == expected
    patch = root / 'patches/koota+0.6.6.patch'
    assert hashlib.sha256(patch.read_bytes()).hexdigest() == '98d01bce8df77c7de4182f875085b4bebd58b3046ab40ebdfaad1d0061053894'


def test_setup_reproduces_exact_upstream_patch_and_is_repeatable(tmp_path):
    root = browser_directory()
    if not graphics_ready() or not shutil.which('git'):
        pytest.skip('Installed graphics dependencies and Git required')
    shutil.copytree(root / 'patches', tmp_path / 'patches')
    files = ('chunk-ZWIGMIL4.js', 'index.cjs', 'react.cjs')
    originals = {}
    for name in files:
        source = root / 'node_modules/koota/dist' / name
        originals[name] = source.read_bytes()
        target = tmp_path / 'node_modules/koota/dist' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    # Restore pristine npm files with the independently vendored upstream diff.
    subprocess.run(['git', '-c', 'core.autocrlf=false', 'apply', '--reverse', '--unsafe-paths',
                    str(tmp_path / 'patches/koota+0.6.6.patch')],
                   cwd=tmp_path, check=True, capture_output=True)
    assert len(apply_dependency_patches(tmp_path)) == 3
    for name in files:
        assert (tmp_path / 'node_modules/koota/dist' / name).read_bytes() == originals[name]
    assert apply_dependency_patches(tmp_path) == []
    (tmp_path / 'patches/koota+0.6.6.patch').write_text('unrecognized patch')
    with pytest.raises(SystemExit, match='Unknown dependency patch'):
        apply_dependency_patches(tmp_path)


def test_installed_runtime_queries_across_trait_generations():
    if not graphics_ready():
        pytest.skip('Installed graphics dependencies required')
    script = '''
      const assert = require('node:assert/strict');
      const {createWorld, trait, Or, createAdded} = require('./node_modules/koota');
      const types = Array.from({length: 100}, () => trait({value: 0}));
      const Marker = trait();
      const Added = createAdded();
      const world = createWorld();
      const query = [Or(types[0], types[99])];
      world.query(...query);
      const tracking = [Or(types[0], types[99]), Added(Marker)];
      world.query(...tracking);
      const first = world.spawn(types[0], Marker);
      const last = world.spawn(types[99], Marker);
      world.spawn(types[50], Marker);
      assert.deepEqual(new Set(world.query(...query)), new Set([first, last]));
      assert.deepEqual(new Set(world.query(...tracking)), new Set([first, last]));
      world.destroy();
    '''
    result = subprocess.run([shutil.which('node'), '-e', script], cwd=browser_directory(),
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
