from __future__ import annotations
import asyncio,json,os
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
P=Path('/home/ah64/Videos/video'); M='/home/ah64/apps/mlt-pipeline/.venv/bin/open-edit-mcp'
E={**os.environ,'OPEN_EDIT_PREVIEW_CHUNKS':'1','OPEN_EDIT_INGEST_ALLOWLIST':'/home/ah64/Videos:/home/ah64/apps/mlt-pipeline'}
def t(r): return '\n'.join(x.text for x in r.content if getattr(x,'type',None)=='text')
async def main():
 async with stdio_client(StdioServerParameters(command=M,args=['--project',str(P)],env=E)) as (r,w):
  async with ClientSession(r,w) as s:
   await s.initialize()
   assets=json.loads(t(await s.call_tool('query_project',{'query':'list_assets','params':{}})))['assets']
   asset=assets[0]
   result=json.loads(t(await s.call_tool('edit_project',{'operation':'add_clip','params':{'asset_hash':asset['hash'],'track_id':'v1','position_sec':0.0,'in_point_sec':0.0,'out_point_sec':asset['duration_s']}})))
   print(json.dumps({'asset':asset,'edit':result},sort_keys=True))
asyncio.run(main())
