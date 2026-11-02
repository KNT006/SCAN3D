"""Source-bound, cancellable RK mesh jobs; no device operations."""
import os,re,json,time,uuid,threading,subprocess,signal,shutil,fcntl
from pathlib import Path
from fastapi import HTTPException,Body
from fastapi.responses import FileResponse,JSONResponse
from common import DATA,CODE,read,job,active
from scan_names import export_stem,named_report

def sources(name):
 root=job(name);found=[]
 from ai_filter_tasks import completed_sources
 for rel in ('combined.npz','current-strategy/combined.npz','review/combined.npz','tail-repaired-v1/combined.npz'):
  p=root/rel
  if p.is_file() and not p.is_symlink():found.append(dict(id=rel.replace('/','__'),label='存档点云 · '+rel,path=str(p),run=name))
 for folder in (DATA/'surface-repairs').glob('*'):
  req=read(folder/'request.json');p=folder/'output/combined.npz'
  if req.get('model','').split(':')[0]==name and read(folder/'output/state.json').get('status')=='complete' and p.is_file():
   found.append(dict(id='surface-'+folder.name,label='已补洞点云 · '+folder.name[:8],path=str(p),run=name))
 for folder in Path('/userdata/afc03-scanner/analysis').glob('*'):
  report=read(folder/'report.json');p=folder/'combined.npz'
  if report.get('source_run')==name and p.is_file() and report.get('version'):
   found.append(dict(id='analysis-'+folder.name,label='已验证重处理 · '+folder.name,path=str(p),run=name))
 found.extend(completed_sources(name))
 return found

def install(app,guard,rpc,replay_busy):
 store=DATA/'mesh-tasks';store.mkdir(exist_ok=True);procs={}
 def folder(identifier):
  if not re.fullmatch('[a-f0-9]{32}',identifier):raise HTTPException(400,'无效 STL 任务编号')
  p=store/identifier
  if not (p/'request.json').is_file():raise HTTPException(404,'STL 任务不存在')
  return p
 def state(p):
  s=read(p/'state.json',{'status':'queued'});req=read(p/'request.json');proc=procs.get(p.name)
  if s['status'] in ('queued','running','stopping') and (proc is None or proc.poll() is not None):
   if proc is None and time.time()-req.get('created',0)<3:return dict(s,id=p.name,request=req,report=None)
   s.update(status='interrupted',error='处理进程已退出；原点云保留，可重新生成')
   (p/'state.json').write_text(json.dumps(s))
  if s['status'] in ('queued','running','stopping'):s['elapsed_seconds']=max(0,time.time()-req['created'])
  return dict(s,id=p.name,request=req,report=read(p/'mesh-report.json') if s['status']=='complete' else None)
 def running():return [p for p in store.iterdir() if (p/'request.json').is_file() and state(p)['status'] in ('queued','running','stopping')]
 @app.middleware('http')
 async def mesh_exclusion(request,call_next):
  if request.method in ('POST','PUT','PATCH','DELETE') and running():
   path=request.url.path
   if not path.endswith('/stop') and path!='/api/scan3d/control':return JSONResponse({'detail':'STL 正在生成，请等待或取消后再进行其他处理'},status_code=409)
  return await call_next(request)
 @app.get('/api/scan3d/runs/{name}/mesh-sources')
 def list_sources(name:str):
  try:return [{k:v for k,v in s.items() if k!='path'} for s in sources(name)]
  except ValueError as e:raise HTTPException(404,str(e))
 @app.get('/api/scan3d/runs/{name}/mesh-tasks')
 def list_tasks(name:str):
  try:job(name)
  except ValueError as e:raise HTTPException(404,str(e))
  rows=[state(p) for p in sorted(store.iterdir(),key=lambda p:p.stat().st_mtime,reverse=True) if read(p/'request.json').get('run')==name]
  # A derived model must not sort behind its parent after an RTC rollback.
  by_id={r['id']:r for r in rows}
  def order(r):
   seen={r['id']};created=r['request'].get('created',0);depth=0;parent=r['request'].get('parent_task')
   while parent in by_id and parent not in seen:
    seen.add(parent);p=by_id[parent];created=max(created,p['request'].get('created',0));depth+=1;parent=p['request'].get('parent_task')
   return created,depth
  return sorted(rows,key=order,reverse=True)[:30]
 @app.post('/api/scan3d/runs/{name}/mesh-tasks',status_code=202)
 def start(name:str,body:dict=Body(...)):
  with guard:
   if set(body)-{'source','quality','close_small_holes','cap_base','depth','samples_per_node','cleanup'}:raise HTTPException(400,'未知 STL 参数')
   cleanup=body.get('cleanup','small')
   if cleanup not in ('main','small','none'):raise HTTPException(400,'无效碎片清理模式')
   quality=body.get('quality','standard')
   if quality not in ('standard','detail'):raise HTTPException(400,'无效质量档位')
   if any(type(body.get(k,False)) is not bool for k in ('close_small_holes','cap_base')):raise HTTPException(400,'补洞和封底须为布尔值')
   depth=body.get('depth',7 if quality=='standard' else 8);samples=body.get('samples_per_node',2)
   if type(depth) is not int or not 4<=depth<=8:raise HTTPException(400,'Poisson 深度须为 4–8 的整数')
   if type(samples) is not int or samples not in (2,8,16):raise HTTPException(400,'曲面降噪须为 2、8 或 16')
   helper=rpc({'op':'status'})
   if active() or helper.get('worker_running') or running() or replay_busy():raise HTTPException(409,'已有扫描或处理任务')
   # Same hardware lock prevents a scan starting during reconstruction.
   lock=None
   try:
    lock=open('/run/lock/afc03-fpga-scan.lock','r');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
   except BlockingIOError:
    if lock:lock.close()
    raise HTTPException(409,'设备或其他处理正在占用，请稍后重试；已有 STL 仍可直接查看')
   except FileNotFoundError:raise HTTPException(503,'扫描互斥锁尚未初始化，请检查开机服务；已有 STL 仍可查看')
   except OSError as e:
    if lock:lock.close()
    raise HTTPException(503,'无法访问扫描互斥锁：'+str(e))
   try:
    candidates=sources(name);source=next((s for s in candidates if s['id']==body.get('source')),None)
    if source is None:raise HTTPException(400,'点云来源不属于所选扫描')
    if Path(source['path']).stat().st_size>128*1024**2:raise HTTPException(400,'点云文件超过板端处理上限')
    if shutil.disk_usage(DATA).free<600*1024**2:raise HTTPException(409,'至少需要 600 MB 可用空间')
    # Source path is chosen exclusively by the server catalog.
    identifier=uuid.uuid4().hex;p=store/identifier;p.mkdir();req=dict(run=name,source=source['id'],source_label=source['label'],source_path=source['path'],quality=quality,cleanup=cleanup,depth=depth,samples_per_node=samples,close_small_holes=body.get('close_small_holes',False),cap_base=body.get('cap_base',False),created=time.time())
    (p/'request.json').write_text(json.dumps(req));(p/'state.json').write_text(json.dumps(dict(status='queued',stage='queued',elapsed_seconds=0)))
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='2',SCAN3D_MESH_LOCK_FD=str(lock.fileno()))
    with (p/'worker.log').open('wb') as log:
     procs[identifier]=subprocess.Popen(['/usr/bin/nice','-n','10','/usr/bin/python3',str(CODE/'mesh_worker.py'),str(p)],env=env,stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=True,pass_fds=(lock.fileno(),))
    return dict(id=identifier,status='queued')
   finally:lock.close()
 @app.get('/api/scan3d/mesh-tasks/{identifier}')
 def get_task(identifier:str):return state(folder(identifier))
 @app.post('/api/scan3d/mesh-tasks/{identifier}/stop')
 def stop(identifier:str):
  with guard:
   p=folder(identifier);proc=procs.get(identifier)
   if proc and proc.poll() is None:
    (p/'STOP').touch();return dict(stop_requested=True)
   return dict(stop_requested=False,status=state(p)['status'])
 @app.get('/api/scan3d/mesh-tasks/{identifier}/files/{kind}')
 def download(identifier:str,kind:str):
  p=folder(identifier);s=state(p)
  if s['status']!='complete':raise HTTPException(409,'STL 尚未完成')
  choices={'stl':'model-mm.stl','report':'mesh-report.json','mesh':'model.ply','original':'unrepaired-mm.stl','removed':'removed-fragments.stl'}
  if kind not in choices:raise HTTPException(404)
  if not (p/choices[kind]).is_file():raise HTTPException(404,'该任务没有此文件')
  source=job(s['request']['run'])
  if kind=='report':return JSONResponse(named_report(source,read(p/choices[kind])))
  return FileResponse(p/choices[kind],filename=export_stem(source)+'-'+identifier[:8]+'-'+choices[kind])
 return running
