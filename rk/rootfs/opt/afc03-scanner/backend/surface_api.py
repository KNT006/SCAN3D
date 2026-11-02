"""Local, opt-in geometry completion. No camera, laser or motor commands."""
import os,json,re,time,uuid,subprocess,signal,math,shutil
from pathlib import Path
import numpy as np
from fastapi import HTTPException
from fastapi.responses import FileResponse,HTMLResponse,JSONResponse
from pydantic import BaseModel,Field,model_validator

class Request(BaseModel):
 model:str
 method:str='mls'
 x:list[float]=Field(min_length=2,max_length=2)
 y:list[float]=Field(min_length=2,max_length=2)
 z:list[float]=Field(min_length=2,max_length=2)
 grid:float=Field(default=.2,ge=.2,le=1)
 polygon_xz:list[list[float]]=Field(default_factory=list,max_length=30)
 @model_validator(mode='after')
 def validate_region(self):
  if self.method not in ('mls','biharmonic'):raise ValueError('未知算法')
  for values in (self.x,self.y,self.z):
   if not all(math.isfinite(v) and abs(v)<=1000 for v in values) or not 4<values[1]-values[0]<=100:raise ValueError('区域范围须为 4–100 mm')
  if (self.x[1]-self.x[0])*(self.z[1]-self.z[0])/self.grid**2>60000:raise ValueError('区域过大，请缩小区域或增大间距')
  if self.method=='biharmonic' and len(self.polygon_xz)<3:raise ValueError('请圈选补洞区域')
  for pt in self.polygon_xz:
   if len(pt)!=2 or not all(math.isfinite(v) for v in pt) or not(self.x[0]<pt[0]<self.x[1] and self.z[0]<pt[1]<self.z[1]):raise ValueError('圈选点必须位于处理范围内')
  if self.method=='biharmonic' and np.linalg.matrix_rank(np.asarray(self.polygon_xz)-np.mean(self.polygon_xz,axis=0))<2:raise ValueError('圈选区域不能共线')
  return self

def install(app,root,lock,busy):
 jobs=(root/'jobs').resolve();data=Path('/userdata/afc03-scanner/jobs').resolve();code=root/'surface-repair/v1';store=data/'surface-repairs';store.mkdir(exist_ok=True);procs={}
 def read(p,default=None):
  try:return json.loads(p.read_text())
  except (OSError,ValueError):return default or {}
 def source(model):
  if not re.fullmatch(r'[A-Za-z0-9_-]{1,90}:(tail-repaired-v1|current-strategy|review)',model):raise HTTPException(400,'无效模型')
  job,variant=model.split(':');p=(jobs/job/variant/'combined.npz').resolve()
  if not any(p.is_relative_to(base) for base in (jobs,data)) or not p.is_file() or p.stat().st_size>128*1024**2:raise HTTPException(404,'模型不存在或过大')
  return p
 def folder(identifier):
  if not re.fullmatch(r'[a-f0-9]{32}',identifier):raise HTTPException(400,'无效任务')
  p=store/identifier
  if not (p/'request.json').is_file():raise HTTPException(404,'任务不存在')
  return p
 def state(p):
  s=read(p/'output/state.json',{'status':'queued'});proc=procs.get(p.name)
  if s.get('status') in ('queued','running') and (proc is None or proc.poll() is not None):
   s.update(status='interrupted',error='任务已停止或服务已重启，可重新创建任务')
  if s.get('status')=='complete':s['audit']=read(p/'output/audit.json')
  return dict(s,id=p.name,request=read(p/'request.json'))
 def active():return [p for p in store.iterdir() if p.is_dir() and state(p).get('status') in ('queued','running')]
 @app.middleware('http')
 async def completion_exclusion(request,call_next):
  if request.method in ('POST','PUT','PATCH','DELETE') and not request.url.path.startswith('/api/surface/') and not request.url.path.endswith('/stop') and active():
   return JSONResponse({'detail':'点云补洞正在运行，请等待完成或先停止补洞'},status_code=409)
  return await call_next(request)
 @app.get('/surface')
 def page():return FileResponse(code/'surface.html')
 @app.get('/api/surface/models')
 def models():
  result=[]
  for job in sorted(jobs.glob('fpga-full-*'),reverse=True):
   for variant in ('tail-repaired-v1','current-strategy','review'):
    p=job/variant/'combined.npz'
    if p.is_file():result.append({'id':job.name+':'+variant,'label':job.name+' / '+variant})
  return result[:40]
 @app.get('/api/surface/preview')
 def preview(model:str):
  with np.load(source(model),allow_pickle=False) as d:
   x=d['xyz'];stride=max(1,len(x)//35000);idx=np.arange(0,len(x),stride)
   return dict(points=np.c_[np.round(x[idx],4),d['rgb'][idx]].tolist(),count=len(x),bounds=[x.min(0).tolist(),x.max(0).tolist()])
 @app.get('/api/surface/tasks')
 def tasks():return [state(p) for p in sorted(store.iterdir(),key=lambda p:p.stat().st_mtime,reverse=True) if p.is_dir() and (p/'request.json').exists()][:30]
 @app.get('/api/surface/tasks/{identifier}')
 def task(identifier:str):return state(folder(identifier))
 @app.post('/api/surface/tasks',status_code=202)
 def start(body:Request):
  with lock:
   if active() or busy():raise HTTPException(409,'已有采集、标定或处理任务，请等待完成')
   if shutil.disk_usage(store).free<300*1024**2:raise HTTPException(409,'可用空间不足 300 MB')
   src=source(body.model);p=store/uuid.uuid4().hex;p.mkdir()
   cfg=body.model_dump();(p/'request.json').write_text(json.dumps(cfg));(p/'config.json').write_text(json.dumps(cfg))
   env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
   with (p/'worker.log').open('wb') as log:
    proc=subprocess.Popen(['/usr/bin/nice','-n','10','/usr/bin/python3',str(code/'surface_worker.py'),'--source',str(src),'--out',str(p/'output'),'--config',str(p/'config.json')],env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
   procs[p.name]=proc
   return {'id':p.name,'status':'queued'}
 @app.post('/api/surface/tasks/{identifier}/stop')
 def stop(identifier:str):
  with lock:
   p=folder(identifier);proc=procs.get(identifier)
   if proc and proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM)
   return {'stop_requested':True}
 @app.get('/api/surface/tasks/{identifier}/files/{kind}')
 def file(identifier:str,kind:str):
  p=folder(identifier);choices={'model':'model.ply','highlight':'duck-tail-highlight-inferred.ply','inferred':'inferred-only.ply','audit':'audit.json','arrays':'combined.npz'}
  if kind not in choices:raise HTTPException(404)
  if state(p).get('status')!='complete':raise HTTPException(409,'结果尚未完成')
  return FileResponse(p/'output'/choices[kind],filename=identifier+'-'+choices[kind])
 @app.get('/api/surface/tasks/{identifier}/viewer')
 def viewer(identifier:str):
  p=folder(identifier)
  if state(p).get('status')!='complete':raise HTTPException(409,'结果尚未完成')
  with np.load(p/'output/combined.npz',allow_pickle=False) as a:
   x=a['xyz'];inferred=a['inferred'];base=np.flatnonzero(inferred==0);added=np.flatnonzero(inferred);ix=np.r_[base[np.linspace(0,len(base)-1,min(50000,len(base))).astype(int)],added]
   data=np.c_[np.round(x[ix],4),a['rgb'][ix],a['laser'][ix],inferred[ix]*3].tolist();lo=x.min(0);hi=x.max(0)
   html=(code/'viewer-template.html').read_text()
   for token,value in {'POINTDATA':json.dumps(data,separators=(',',':')),'CENTER':json.dumps(((lo+hi)/2).tolist()),'RADIUS':str(max(hi-lo)*.52),'FULLCOUNT':str(len(x)),'BASECOUNT':str(len(base)),'ADDCOUNT':str(len(added))}.items():html=html.replace(token,value)
   return HTMLResponse(html,headers={'Cache-Control':'no-store'})
