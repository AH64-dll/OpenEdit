"""Re-transcribe project assets and persist word-level alignment to sidecars."""
from pathlib import Path
from open_edit.storage.assets import AssetStore
from open_edit.storage.transcription import transcribe

ASSETS_DIR = Path("/home/ah64/OpenEditProjects/ll/.open_edit/assets")
HASHES = [
    "f6f74b418b22402f8a4209fa910c35a3010516da91f84180395d9097ae835486",  # 1.mp4
    "81b7206760911344d456c0e82fc4e2bf16fddcab3f7a0d8ddcb387cb10c908ce",  # 2.mp4
    "6cc0476493762d1e8f42ca0393bb440bca7bdaf3e3dd1a63be9898cb4b1958ff",  # 3.mp4
]

store = AssetStore(ASSETS_DIR)
for h in HASHES:
    asset = store.get(h)
    if asset is None:
        print("MISSING", h)
        continue
    alignment = transcribe(Path(asset.stored_path))
    print(h[:8], "words:", len(alignment))
    asset = asset.model_copy(update={"alignment": alignment})
    sidecar = ASSETS_DIR / h[:2] / f"{h}.meta.json"
    sidecar.write_text(asset.model_dump_json(indent=2))
print("done")
