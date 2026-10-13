"""Assemble the public guide and the verified demo from their repository sources."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build(output: Path) -> None:
    guide = ROOT / 'docs' / 'guide'
    example = ROOT / 'examples' / 'openedit-explainer'
    output = output.resolve()
    if output == ROOT or output.is_relative_to(guide) or output.is_relative_to(example):
        raise ValueError('Choose a separate build output directory')
    shutil.copytree(guide, output, dirs_exist_ok=True, ignore=shutil.ignore_patterns('README.md'))
    media = output / 'media'
    media.mkdir(exist_ok=True)
    for source, target in [('preview.mp4', 'openedit-trailer.mp4'),
                           ('poster.png', 'poster.png'),
                           ('openedit-kinetic-project.zip', 'openedit-kinetic-project.zip')]:
        shutil.copy2(example / source, media / target)
    (output / '.nojekyll').touch()
    print(f'Built OpenEdit site at {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
