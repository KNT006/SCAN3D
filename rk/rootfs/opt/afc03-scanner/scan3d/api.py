import sys,json,socket,subprocess,uuid,time,threading,shutil,zipfile
from functools import wraps
from pathlib import Path
import numpy as np
from fastapi import HTTPException,Body,Request
from fastapi.responses import FileResponse,Response,JSONResponse,StreamingResponse
sys.path.insert(0,'/opt/afc03-scanner/scan3d')
sys.path.insert(0,'/opt/afc03-scanner/fpga')
from common import *
from storage_guard import status as storage_status
from task_state import task_state
from run_access import acquire as acquire_run
from preview_stream import relay_mjpeg
from spatial_filter import validate as spatial_validate
from scan_names import rename_scan,export_stem,named_report
import urllib.request
def install(app,root):
 store=DATA/'scan3d-work';store.mkdir(exist_ok=True);workers={};guard=threading.Lock();cache={}
 mesh_running=lambda:[]
 ai_running=lambda:False
 def serialized(fn):
  @wraps(fn)
  def wrapped(*args,**kwargs):
   with guard:return fn(*args,**kwargs)
  return wrapped
 @app.middleware('http')
 async def scan3d_exclusion(request,call_next):
  if request.method in ('POST','PUT','PATCH','DELETE') and active():
   if request.url.path not in ('/api/scan3d/control','/api/scan3d/replay') and not re.fullmatch(r'/api/scan3d/runs/[A-Za-z0-9_-]{1,100}/cleanup-(preview|execute)',request.url.path) and not request.url.path.endswith('/stop'):
    return JSONResponse({'detail':'扫描正在运行，设备与参数已锁定'},status_code=409)
  response=await call_next(request)
  # The HTML entry must not retain an old bundle list across kiosk restarts.
  # Hashed JS/CSS and archived result files keep their existing cache behavior.
  if request.url.path in ('/','/index.html'):
   response.headers['Cache-Control']='no-store, max-age=0, must-revalidate'
   response.headers['Pragma']='no-cache'
   response.headers['Expires']='0'
  return response
 def rpc(d):
  try:
   with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
    s.settimeout(2 if d.get('op')=='status' else 100);s.connect('/run/afc03-scan3d.sock');s.sendall(json.dumps(d).encode()+b'\n');data=b''
    while not data.endswith(b'\n'):
     chunk=s.recv(65536)
     if not chunk:raise ValueError('控制服务连接中断')
     data+=chunk
   reply=json.loads(data)
   if not reply['ok']:raise ValueError(reply['error'])
   return reply['result']
  except Exception as e:raise HTTPException(409,str(e))
 def safejob(name):
  try:return job(name)
  except ValueError as e:raise HTTPException(404,str(e))
 def cloud_path(p):
  for rel in ('combined.npz','current-strategy/combined.npz','review/combined.npz','tail-repaired-v1/combined.npz'):
   if (p/rel).is_file():return p/rel
 def jobs():
  cached=cache.get('history')
  if cached and time.monotonic()-cached[0]<5:return cached[1]
  result=[];running=active()
  for p in DATA.iterdir():
   if not p.is_dir() or p.is_symlink():continue
   st=read(p/'status.json')
   if not st or not ((p/'bundle').is_dir() or cloud_path(p)):continue
   count=st.get('completed_positions',0)
   live=bool(running and running==p)
   if st.get('status')=='running' and not live:st=dict(st,status='interrupted')
   result.append(dict(id=p.name,title=st.get('title',st.get('object_name',p.name)),state=st.get('status'),live=live,completed=count,elapsed=st.get('elapsed_seconds'),passed=st.get('passed',False),closure=st.get('closure'),step=st.get('requested_step_deg'),modified=p.stat().st_mtime,model_available=bool(cloud_path(p)),supplemental_closure=read(p/'delivery.json').get('supplemental_closure_passed',False)))
  def order(x):
   m=re.search(r'(20\d{6})-(\d{6})',x['id'])
   return (m.group(1)+m.group(2)) if m else str(x['modified'])
  result=sorted(result,key=order,reverse=True)[:100];cache['history']=(time.monotonic(),result)
  return result
 @app.get('/api/scan3d/status')
 def status():
  free=shutil.disk_usage(DATA);p=active()
  try:helper=rpc({'op':'status'})
  except HTTPException:helper={'unavailable':True}
  name=p.name if p else helper.get('last_job') if helper.get('worker_running') else None
  st=task_state(DATA/name,True) if name else {}
  roi_config=read((DATA/name/'bundle/config.json') if name else FPGA/'new-strategy-bundle/config.json')
  return dict(scan_roi=roi_config.get('scan_roi'),active=name,scan=st,helper=helper,mesh_processing=bool(mesh_running()) or ai_running(),ai_processing=ai_running(),storage=storage_status(),fpga_color_correction=False,parameters={k:dict(default=v[0],min=v[1],max=v[2],scope='RK 单帧回放；不修改当前 FPGA') for k,v in PARAMS.items()})
 @app.get('/api/scan3d/preview.mjpeg')
 async def continuous_preview():
  base=os.environ.get('SCANNER_CAMERA_URL','http://127.0.0.1:8080')
  return StreamingResponse(relay_mjpeg(base),media_type='multipart/x-mixed-replace; boundary=frame',headers={'Cache-Control':'no-store, max-age=0','X-Accel-Buffering':'no'})
 @app.get('/api/scan3d/preview.jpg')
 def preview():
  # Read the existing JPEG producer, never trigger acquisition or alter controls.
  base=os.environ.get('SCANNER_CAMERA_URL','http://127.0.0.1:8080')
  try:
   with urllib.request.urlopen(base+'/status',timeout=.8) as r:info=json.load(r)
   if info.get('age',999)>2:raise ValueError('相机预览帧已过期')
   with urllib.request.urlopen(base+'/snapshot.jpg',timeout=1.2) as r:data=r.read()
   if not data.startswith(b'\xff\xd8'):raise ValueError('相机预览数据无效')
  except Exception as e:raise HTTPException(503,'相机预览暂不可用：'+str(e))
  return Response(data,media_type='image/jpeg',headers={'Cache-Control':'no-store, max-age=0','X-Preview-Stream':str(info.get('stream_id',''))})
 @app.get('/api/scan3d/runs/{name}/state')
 def run_state(name:str):
  if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',name):raise HTTPException(400,'无效扫描编号')
  p=DATA/name
  if p.is_symlink():raise HTTPException(404,'扫描不存在')
  running=active();alive=running==p
  if not alive:
   try:
    helper=rpc({'op':'status'});alive=helper.get('worker_running') and helper.get('last_job')==name
   except HTTPException:pass
  if not p.is_dir() and not alive:raise HTTPException(404,'扫描不存在')
  return task_state(p,alive)
 @app.get('/api/scan3d/runs')
 def runs():return jobs()
 @app.get('/api/scan3d/profile')
 def profile():return read(store/'candidate-profile.json',parameters({}))
 @app.post('/api/scan3d/profile')
 def save_profile(body:dict=Body(...)):
  try:p=parameters(body)
  except ValueError as e:raise HTTPException(400,str(e))
  target=store/'candidate-profile.json';temp=target.with_suffix('.tmp');temp.write_text(json.dumps(p));temp.replace(target)
  return dict(saved=True,scope='候选回放参数；未应用于正式扫描')
 @app.get('/api/scan3d/spatial-profile')
 def spatial_profile():return rpc({'op':'spatial_profile'})
 @app.post('/api/scan3d/spatial-profile')
 def save_spatial(body:dict=Body(...)):
  try:cfg=spatial_validate(body)
  except ValueError as e:raise HTTPException(400,str(e))
  return rpc({'op':'save_spatial','profile':cfg})
 @app.get('/api/scan3d/camera-controls')
 def camera_controls():return rpc({'op':'controls'})
 @app.post('/api/scan3d/control')
 def control(body:dict=Body(...)):
  if ai_running() and body.get('op')!='stop':raise HTTPException(409,'AI 点云过滤正在运行；可以使用停止按钮')
  if body.get('op') not in ('lights','camera','move','scan','capture','stop','resume','recover_manual_motion'):raise HTTPException(400,'未知操作')
  if mesh_running() and body.get('op')!='stop':raise HTTPException(409,'STL 正在生成，请等待或取消后操作设备')
  if any(p.poll() is None for p in workers.values()) and body.get('op')!='stop':raise HTTPException(409,'帧回放正在运行，请等待完成')
  return rpc(body)
 @app.post('/api/scan3d/runs/{name}/cleanup-preview')
 @serialized
 def cleanup_preview(name:str,body:dict=Body(...)):
  safejob(name)
  return rpc(dict(op='cleanup_preview',name=name,mode=body.get('mode')))
 @app.post('/api/scan3d/runs/{name}/cleanup-execute')
 @serialized
 def cleanup_execute(name:str,body:dict=Body(...)):
  safejob(name)
  return rpc(dict(op='cleanup_execute',name=name,mode=body.get('mode'),token=body.get('token'),confirm=body.get('confirm'),acknowledged=body.get('acknowledged')))
 @app.post('/api/scan3d/runs/{name}/rename')
 @serialized
 def rename(name:str,body:dict=Body(...)):
  p=safejob(name)
  if active() or mesh_running() or any(w.poll() is None for w in workers.values()):raise HTTPException(409,'请等待扫描或分析任务完成后重命名')
  helper=rpc({'op':'status'})
  if helper.get('worker_running'):raise HTTPException(409,'扫描正在运行，请稍后重命名')
  fd=None
  try:
   fd=acquire_run(name,exclusive=True)
   result=rename_scan(p,body.get('title'));cache.pop('history',None);return result
  except ValueError as e:raise HTTPException(400,str(e))
  finally:
   if fd is not None:os.close(fd)
 @app.get('/api/scan3d/runs/{name}/details')
 def details(name:str,include_cloud:bool=True):
  from image_retention import available_positions
  p=safejob(name);st=read(p/'status.json');file=cloud_path(p);bounds=None;count=0
  if file and include_cloud:
   with np.load(file,allow_pickle=False) as d:
    xyz=d['xyz'] if 'xyz' in d else d['axis_frame_mm'];count=len(xyz)
    if count:bounds=np.ptp(xyz,axis=0).round(3).tolist()
  reports=[x for x in ('status.json','acceptance-audit.json','timing-summary.json','delivery.json','review-model.json') if (p/x).is_file()]
  return dict(id=name,state=st,timing=read(p/'timing-summary.json'),supplemental_closure=read(p/'delivery.json').get('supplemental_closure_passed',False),count=count if include_cloud else None,bounds_mm=bounds,model_summary_loaded=include_cloud,bounds_scope='坐标轴包围盒尺寸，非计量精度；缺失点与离群点会影响结果',accuracy_validated=False,reports=reports,image_positions=available_positions(p),positions=[int(x.name.split('-')[-1]) for x in sorted(p.glob('position-*'),key=lambda q:int(q.name.split('-')[-1])) if (x/'status.json').is_file()])
 @app.get('/api/scan3d/runs/{name}/cloud.bin')
 def result_cloud(name:str,request:Request):
  from cloud_binary import build_cloud
  p=safejob(name)
  if active()==p:raise HTTPException(409,'扫描进行中，请在实时监控查看；完成后可整体显示')
  source=cloud_path(p)
  if source is None:
   last=read(p/'status.json').get('planned_intervals')
   source=[f for q in sorted(p.glob('position-*'),key=lambda q:int(q.name.split('-')[-1])) if read(q/'status.json').get('status')=='complete' and not(last and q.name==f'position-{last:03d}') for f in (q/'A/points.npz',q/'B/points.npz') if f.is_file()]
   if not source:raise HTTPException(404,'尚无已保存点云')
  target,info=build_cloud(p,source)
  from cloud_binary import cloud_response
  return cloud_response(target,info,request.headers.get('if-none-match'))

 @app.get('/api/scan3d/runs/{name}/points')
 def points(name:str,after:int=-1,retry:str='',v:int=1):
  if v!=2:raise HTTPException(409,'实时预览已更新，请刷新页面后继续显示')
  from live_preview import preview_page
  try:return preview_page(safejob(name),after,retry)
  except ValueError as e:raise HTTPException(400,str(e))
 @app.get('/api/scan3d/runs/{name}/image/{index}/{role}')
 def image(name:str,index:int,role:str):
  if role not in ('OFF','A','B','COLOR') or not 0<=index<=3200:raise HTTPException(400)
  p=safejob(name)/f'position-{index:03d}'/role
  for ext in ('png','ppm'):
   file=p/('same-frame.'+ext)
   if file.exists():
    if ext=='png':return FileResponse(file)
    import cv2
    im=cv2.imread(str(file));ok,data=cv2.imencode('.png',im);return Response(data.tobytes(),media_type='image/png')
  raise HTTPException(404,'图像尚未保存')
 @app.get('/api/scan3d/runs/{name}/report/{filename}')
 def report(name:str,filename:str):
  if filename not in ('status.json','acceptance-audit.json','timing-summary.json','delivery.json','review-model.json','scan3d-archive.zip'):raise HTTPException(400)
  p=safejob(name)/filename
  if not p.exists():raise HTTPException(404)
  if filename.endswith('.json'):return JSONResponse(named_report(p.parent,read(p)))
  return FileResponse(p,filename=export_stem(p.parent)+'-archive.zip')
 @app.post('/api/scan3d/runs/{name}/archive')
 @serialized
 def archive(name:str):
  if active():raise HTTPException(409,'扫描中暂不归档')
  p=safejob(name);target=p/'scan3d-archive.zip'
  files=[x for x in p.glob('*.json') if x.is_file()]+list((p/'bundle').glob('*.json'))
  files += [x for x in (cloud_path(p),p/'combined-color.ply') if x and x.is_file()]
  mesh_files=[f for d in (DATA/'mesh-tasks').glob('*') if read(d/'request.json').get('run')==name and read(d/'state.json').get('status')=='complete' for f in (d/'request.json',d/'mesh-report.json',d/'model-mm.stl') if f.is_file()]
  if sum(x.stat().st_size for x in files+mesh_files)>200*1024**2 or shutil.disk_usage(DATA).free<300*1024**2:raise HTTPException(409,'归档空间不足或文件过大')
  try:
   with zipfile.ZipFile(str(target)+'.tmp','w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
    for x in files:
     if x.suffix=='.json':z.writestr(str(x.relative_to(p)),json.dumps(named_report(p,read(x)),ensure_ascii=False,indent=2))
     else:z.write(x,x.relative_to(p))
    for x in mesh_files:
     rel='stl-tasks/'+x.parent.name+'/'+x.name
     if x.suffix=='.json':z.writestr(rel,json.dumps(named_report(p,read(x)),ensure_ascii=False,indent=2))
     else:z.write(x,rel)
    z.writestr('ARCHIVE-SCOPE.txt','Model, calibration and reports only. Raw photos remain on the board. No source files were deleted.')
   os.replace(str(target)+'.tmp',target)
  except Exception:
   Path(str(target)+'.tmp').unlink(missing_ok=True);raise
  return dict(url=f'/api/scan3d/runs/{name}/report/scan3d-archive.zip')
 @app.get('/api/scan3d/meshes')
 def meshes():
  base=root/'frontend/dist/results'
  return [dict(name=p.parent.name+'/'+p.name,url='/results/'+p.relative_to(base).as_posix()) for p in sorted(base.glob('*/*.stl'))+sorted(base.glob('*/*/*.stl'))]
 @app.get('/api/scan3d/replay-policy')
 def replay_policy():
  from rgb_adaptive_strategy import SETTINGS
  from rk_candidate_policy import VERSION
  from near_peak_policy import SETTINGS as NEAR
  return dict(version=VERSION,settings=SETTINGS,near=NEAR,multipeak_enabled=False,long_track_mode='advisory_only')
 @app.post('/api/scan3d/replay')
 def replay(body:dict=Body(...)):
  with guard:
   if any(p.poll() is None for p in workers.values()):raise HTTPException(409,'上一帧回放尚未完成')
   p=safejob(body.get('run',''));index=body.get('index',0);laser=body.get('laser','A')
   running=active();helper=rpc({'op':'status'})
   if running==p or (helper.get('worker_running') and helper.get('last_job')==p.name):raise HTTPException(409,'不能分析正在采集的扫描，请选择其他已保存扫描')
   mem={line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
   if mem.get('MemAvailable',0)<512*1024:raise HTTPException(409,'可用内存不足 512 MiB，稍后再分析历史帧')
   if type(index)!=int or not 0<=index<=3200 or laser not in ('A','B'):raise HTTPException(400,'无效帧')
   if body.get('mode')!='current_scan' or body.get('parameters') or body.get('spatial'):raise HTTPException(409,'流程页已升级为实际扫描策略回放，请刷新页面；不接受旧多峰试验参数')
   if not (p/f'position-{index:03d}'/laser/'frame.json').exists():raise HTTPException(404,'此位置没有激光数据')
   if not all((p/f'position-{index:03d}'/laser/file).is_file() for file in ('records.bin','hardware-frame.json')):
    raise HTTPException(409,'此帧未保存 FPGA 候选和原始帧头，无法按当前策略回放')
   try:fd=acquire_run(p.name)
   except ValueError as e:raise HTTPException(409,str(e))
   try:
    identifier=uuid.uuid4().hex;folder=store/identifier;folder.mkdir();req=dict(run=p.name,index=index,laser=laser,mode='current_scan')
    (folder/'request.json').write_text(json.dumps(req))
    with (folder/'worker.log').open('wb') as log:workers[identifier]=subprocess.Popen(['/usr/bin/nice','-n','10','/usr/bin/python3',str(CODE/'replay.py'),str(folder)],stdout=log,stderr=log,env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'),pass_fds=(fd,))
    return dict(id=identifier)
   finally:os.close(fd)
 @app.get('/api/scan3d/replay/{identifier}')
 def replay_state(identifier:str):
  if not re.fullmatch('[a-f0-9]{32}',identifier):raise HTTPException(400)
  folder=store/identifier
  if not folder.exists():raise HTTPException(404)
  if (folder/'result.json').exists():return read(folder/'result.json')
  proc=workers.get(identifier)
  if proc and proc.poll() is None:return dict(status='running')
  return dict(status='failed',error=(folder/'worker.log').read_text()[-1000:])
 @app.get('/api/scan3d/replay/{identifier}/row/{y}')
 def replay_row(identifier:str,y:int):
  if not re.fullmatch('[a-f0-9]{32}',identifier):raise HTTPException(400,'无效回放编号')
  folder=store/identifier;result=read(folder/'result.json')
  if result.get('status')!='complete':raise HTTPException(409,'请先完成此帧分析')
  left,top,right,bottom=result['roi']
  if not top<=y<bottom:raise HTTPException(400,'所选行不在 ROI 内')
  if result.get('replay_version')!='scan-flow-shared-v1':raise HTTPException(409,'此回放为旧版本，请重新分析此帧')
  curves=None
  if result.get('row_profiles_available') and (folder/'row-profiles.npz').exists():
   with np.load(folder/'row-profiles.npz',allow_pickle=False) as a:curves=dict(zip(('on','off','signal','smooth'),a['profiles'][y-top].tolist()))
  detail=read(folder/'row-audit.json')[str(y)]
  return dict(**detail,spatial_filter=result.get('spatial_filter'),x_origin=left,curves=curves,parameters=result['stripe_settings'],ground=result['ground'],replay_id=identifier,source=result['request'],color_source=result['color_source'],signal_definition='max(max(Ron-Roff,0),max(Gon-Goff,0),max(Bon-Boff,0))',smooth_scale=16)
 from mesh_tasks import install as install_mesh_tasks
 mesh_running=install_mesh_tasks(app,guard,rpc,lambda:any(p.poll() is None for p in workers.values()))
 from ai_filter_tasks import install as install_ai_filter
 ai_running=install_ai_filter(app,guard,lambda:bool(mesh_running()) or any(p.poll() is None for p in workers.values()))
 from color_preview import install as install_color_preview
 install_color_preview(app,DATA)
