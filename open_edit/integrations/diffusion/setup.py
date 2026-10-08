"""Install the optional compiler worker: python -m ...diffusion.setup."""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
from pathlib import Path

from open_edit.integrations.diffusion.compiler import worker_directory


def apply_dependency_patches(directory: Path) -> list[str]:
    """Apply vendored dependency patches after `npm ci --ignore-scripts`.

    Upstream ships patches/*.patch applied through patch-package's postinstall
    hook, which `--ignore-scripts` deliberately never runs. Each patch file is
    the manifest: it names the node_modules targets, and the fix is applied as
    exact anchored text substitutions (no git required, deterministic under
    npm's reproducible layout). Context mismatches or unknown patch content
    fail loudly instead of silently installing a broken tree.
    """
    applied = []
    for patch in sorted((directory / 'patches').glob('*.patch')):
        digest = hashlib.sha256(patch.read_bytes()).hexdigest()
        files = _PATCH_TRANSFORMS.get(digest)
        if files is None:
            raise SystemExit(f'Unknown dependency patch {patch.name}: update _PATCH_TRANSFORMS in open_edit/integrations/diffusion/setup.py')
        for name, transforms in files.items():
            target = directory / 'node_modules' / name
            if not target.is_file():
                raise SystemExit(f'{patch.name} targets missing file {name} under {directory}')
            if _apply_transforms(target, transforms):
                applied.append(f'{patch.name} -> {name}')
    return applied


# sha256 of patches/koota+0.6.6.patch (upstream diffusionstudio/editor @ fefcde9d)
# -> per-file anchored substitutions fixing Or queries across trait generations.
_KOOTA_DECL = b'  let staticHasOr = false;\n  let staticOrMatched = false;\n'
_KOOTA_OR_OLD = b'    if (or !== 0 && (entityMask & or) === 0) return false;\n'
_KOOTA_OR_NEW = (b'    if (or !== 0) {\n      staticHasOr = true;\n'
                 b'      if ((entityMask & or) !== 0) staticOrMatched = true;\n    }\n')
_KOOTA_GUARD = b'  if (staticHasOr && !staticOrMatched) return false;\n'
_PATCH_TRANSFORMS = {
    '98d01bce8df77c7de4182f875085b4bebd58b3046ab40ebdfaad1d0061053894': dict.fromkeys(
        ('koota/dist/chunk-ZWIGMIL4.js', 'koota/dist/index.cjs', 'koota/dist/react.cjs'),
        (b'function checkQuery(', b'function checkQueryTracking('),
    ),
}


def _patch_function(body: bytes, signature: bytes, early_return: bytes) -> bytes:
    """Apply the koota static-Or fix to one function body."""
    if _KOOTA_GUARD in body:
        return body  # already patched
    if body.count(early_return) != 1 or body.count(_KOOTA_OR_OLD) != 1:
        raise SystemExit(f'koota patch anchors not found after {signature!r}: dependency content changed')
    body = body.replace(early_return, early_return + _KOOTA_DECL, 1)
    body = body.replace(_KOOTA_OR_OLD, _KOOTA_OR_NEW, 1)
    tail_marker = (b'\n  let hasOrGroup = false;\n'
                   if signature == b'function checkQueryTracking('
                   else b'\n  return true;\n')
    index = body.index(tail_marker)
    return body[:index] + b'\n' + _KOOTA_GUARD + body[index + 1:]


def _apply_transforms(target: Path, signatures: tuple[bytes, ...]) -> bool:
    content = target.read_bytes()
    if len(signatures) == 0:
        raise SystemExit(f'empty transform for {target}')
    start = 0
    changed = False
    for signature in signatures:
        position = content.index(signature, start)
        next_fn = content.find(b'\nfunction ', position + 1)
        end = next_fn if next_fn != -1 else len(content)
        early_return = (b'  if (query.traitInstances.all.length === 0) return false;\n'
                        if signature == b'function checkQuery('
                        else b'  if (traitInstancesAll.length === 0) return false;\n')
        patched = _patch_function(content[position:end], signature, early_return)
        if patched != content[position:end]:
            content = content[:position] + patched + content[end:]
            changed = True
            start = position + len(patched)
    if changed:
        target.write_bytes(content)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description='Install optional pinned Diffusion workers')
    parser.add_argument('--graphics', action='store_true', help='also install the browser graphics worker')
    parser.add_argument('--chromium', action='store_true', help='also download the pinned Chromium browser')
    args = parser.parse_args()
    npm = shutil.which('npm')
    if not npm:
        raise SystemExit('Node.js and npm are required for optional Diffusion authoring')
    subprocess.run(
        [npm, 'ci', '--ignore-scripts', '--no-audit', '--no-fund'],
        cwd=worker_directory(), check=True, timeout=180,
    )
    print('Diffusion authoring worker installed')
    if args.graphics or args.chromium:
        from open_edit.integrations.diffusion.graphics import browser_directory

        directory = browser_directory()
        subprocess.run([npm, 'ci', '--ignore-scripts', '--no-audit', '--no-fund'],
                       cwd=directory, check=True, timeout=180)
        applied = apply_dependency_patches(directory)
        for name in applied:
            print(f'Applied dependency patch {name}')
        if args.chromium:
            node = shutil.which('node')
            subprocess.run([node, str(directory / 'node_modules/playwright-core/cli.js'), 'install', 'chromium'],
                           cwd=directory, check=True, timeout=300)
        print('Diffusion graphics worker installed')


if __name__ == '__main__':
    main()
