"""Seed real CAS media for browser acceptance; no provider or transcription."""
import json
import sys
from pathlib import Path

from PIL import Image

from open_edit.ir.types import AddClipOp
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore

root = Path(sys.argv[1]) / 'authoring-review'
root.mkdir(parents=True)
image = root / 'hero.png'
Image.new('RGB', (640, 360), '#2779c3').save(image)
asset = AssetStore(root / '.open_edit/assets').ingest(str(image), transcribe=False)
store = EditGraphStore(root / '.open_edit/edit_graph.db')
store.append(AddClipOp(author='user', clip_id='hero', asset_hash=asset.asset_hash,
                       track_id='main', position_sec=0, out_point_sec=2))
print(json.dumps({'project_path': str(root)}))
