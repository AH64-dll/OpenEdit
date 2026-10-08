"""Execute fresh TSX through the independent legacy package and frame server."""
from __future__ import annotations

import io
import shutil
from pathlib import Path

import pytest
from PIL import Image

from open_edit.render.profiles import RenderProfile
from open_edit.render.remotion import render_composition
from open_edit.render.remotion.frame_engine import FramePullClient, FrameRequest


@pytest.mark.browser
def test_optional_legacy_package_renders_tsx_and_pulls_frame(tmp_path, monkeypatch):
    legacy = Path(__file__).parents[1] / 'open_edit/integrations/remotion'
    if not (legacy / 'node_modules/@remotion/renderer/package.json').is_file():
        pytest.skip('explicit optional legacy-remotion setup required')
    assert shutil.which('node') and shutil.which('ffprobe')
    monkeypatch.delenv('OPEN_EDIT_REMOTION_BIN', raising=False)
    monkeypatch.delenv('OPEN_EDIT_REMOTION_CLI', raising=False)
    source = tmp_path / '.open_edit/remotion/src'
    source.mkdir(parents=True)
    (source / 'index.tsx').write_text('''
import React from 'react';
import {registerRoot, Composition} from 'remotion';
const Card = () => <div style={{width:'100%',height:'100%',background:'#ff0000'}}/>;
registerRoot(() => <Composition id="TitleCard" component={Card} width={64} height={64} fps={30} durationInFrames={2}/>);
''')
    # No project node_modules or config changes are required.
    result = render_composition(tmp_path, entry_point='src/index.tsx', composition_id='TitleCard',
        props={}, output_path=tmp_path / 'legacy.mp4',
        profile=RenderProfile(name='legacy-test', width=64, height=64, frame_rate_num=30, frame_rate_den=1),
        timeout_s=120)
    assert result.ok and Path(result.output_path).stat().st_size > 0
    with FramePullClient.for_project(tmp_path, timeout_s=120) as client:
        frame = client.request_frame(FrameRequest(request_id='real', composition_id='TitleCard',
            entry_point='src/index.tsx', props={}, frame=0, width=64, height=64, fps=30, alpha=False))
    pixel = Image.open(io.BytesIO(frame.bytes)).convert('RGB').getpixel((32, 32))
    assert pixel[0] > 240 and pixel[1] < 10 and pixel[2] < 10
    assert not (tmp_path / 'node_modules').exists()
    assert not (tmp_path / '.open_edit/remotion/node_modules').exists()
