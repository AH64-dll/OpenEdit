"""Small moving textured target with deterministic source-space ground truth."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from open_edit.ir.types import AddClipOp
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore

root = Path(sys.argv[1]) / 'object-tracking-review'
root.mkdir(parents=True)
media = root / 'moving.mkv'
process = subprocess.Popen(['ffmpeg','-y','-v','error','-f','rawvideo','-pix_fmt','rgb24',
    '-s','320x180','-r','15','-i','-','-c:v','ffv1',str(media)],stdin=subprocess.PIPE)
texture = Image.fromarray(np.random.default_rng(42).integers(100,255,size=(36,48,3),dtype=np.uint8))
ImageDraw.Draw(texture).rectangle((2,2,45,33),outline='#fff',width=2)
for index in range(60):
    image = Image.new('RGB',(320,180),'#15202b')
    image.paste(texture,(round(20+35*index/15),round(65+8*np.sin(index/15*2))))
    process.stdin.write(image.tobytes())
process.stdin.close()
assert process.wait(timeout=30) == 0
asset = AssetStore(root / '.open_edit/assets').ingest(str(media),transcribe=False)
store = EditGraphStore(root / '.open_edit/edit_graph.db')
store.append(AddClipOp(author='user',clip_id='hero',asset_hash=asset.asset_hash,track_id='main',position_sec=0,out_point_sec=4))
print(json.dumps({'project_path':str(root)}))
