"""Seed real CAS media for browser acceptance; no provider or transcription."""
import json
import subprocess
import sys
from pathlib import Path

from open_edit.ir.types import AddClipOp
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore

root = Path(sys.argv[1]) / 'authoring-review'
root.mkdir(parents=True)
media = root / 'hero.mp4'
subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i',
                'color=c=0x2779c3:s=640x360:r=30', '-t', '2', '-c:v', 'libx264',
                '-pix_fmt', 'yuv420p', str(media)], check=True)
asset = AssetStore(root / '.open_edit/assets').ingest(str(media), transcribe=False)
store = EditGraphStore(root / '.open_edit/edit_graph.db')
store.append(AddClipOp(author='user', clip_id='hero', asset_hash=asset.asset_hash,
                       track_id='main', position_sec=0, out_point_sec=2))
print(json.dumps({'project_path': str(root)}))
