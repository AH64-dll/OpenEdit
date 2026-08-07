from __future__ import annotations
import asyncio,json,os,time
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from open_edit.storage.edit_graph import EditGraphStore
P=Path('/home/ah64/Videos/video'); M='/home/ah64/apps/mlt-pipeline/.venv/bin/open-edit-mcp'
E={**os.environ,'OPEN_EDIT_PREVIEW_CHUNKS':'1','OPEN_EDIT_HYPERFRAMES_BIN':'/home/ah64/apps/mlt-pipeline/node_modules/.bin/hyperframes','OPEN_EDIT_NODE_BIN':'/usr/bin/node'}
def t(r): return '\n'.join(x.text for x in r.content if getattr(x,'type',None)=='text')
async def wait(s,jid):
 started=time.monotonic()
 while True:
  j=json.loads(t(await s.call_tool('get_render_job',{'job_id':jid})))
  if j.get('status') in {'succeeded','failed','cancelled','orphaned'}: return j,time.monotonic()-started
  await asyncio.sleep(.5)
async def main():
 ids=set(); template=P/'latency_smoke.html'; template.write_text('<div id="title" style="width:100%;height:100%;font:30px sans-serif;color:white">{{title}}</div>',encoding='utf-8')
 try:
  async with stdio_client(StdioServerParameters(command=M,args=['--project',str(P)],env=E)) as (r,w):
   async with ClientSession(r,w) as s:
    await s.initialize(); a=json.loads(t(await s.call_tool('query_project',{'query':'list_assets','params':{}})))['assets'][0]
    await s.call_tool('edit_project',{'operation':'add_clip','params':{'asset_hash':a['hash'],'track_id':'v1','position_sec':0,'in_point_sec':0,'out_point_sec':12}})
    await s.call_tool('edit_project',{'operation':'add_hyperframes_overlay','params':{'template_path':template.name,'variables':{'title':'latency'},'position_sec':0,'duration_sec':2}})
    ids={op.edit_id for op in EditGraphStore(P/'.open_edit'/'edit_graph.db').load_all() if op.status=='applied'}
    results=[]
    for start in (0.0,10.0):
     en=json.loads(t(await s.call_tool('trigger_render',{'mode':'preview-chunks','ranges':[{'start_sec':start,'end_sec':start+2}],'media':'video','priority':'interactive','wait':False})))
     j,elapsed=await wait(s,en['job_id']); results.append({'range':[start,start+2],'elapsed_sec':elapsed,'status':j.get('status'),'result':j.get('result')})
    print(json.dumps(results,default=str),flush=True)
 finally:
  template.unlink(missing_ok=True); store=EditGraphStore(P/'.open_edit'/'edit_graph.db')
  for op in store.load_all():
   if op.edit_id in ids and op.status=='applied': store.update_status(op.edit_id,'reverted',reason='preview latency smoke cleanup')
  print('active_ops',sum(op.status=='applied' for op in store.load_all()),flush=True)
asyncio.run(main())
