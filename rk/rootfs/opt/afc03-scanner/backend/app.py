"""LAN reconstruction and finite, operator-confirmed board acquisition."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
import shutil
from urllib.parse import urlsplit

import numpy as np
import cv2
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import FileResponse,JSONResponse,Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

ROOT=Path(os.environ.get('SCANNER_ROOT','/opt/afc03-scanner'))
DATA=ROOT/'data';JOBS=ROOT/'jobs';JOBS.mkdir(parents=True,exist_ok=True)
CAMERA_URL=os.environ.get('SCANNER_CAMERA_URL','http://192.168.1.89:8080')
app=FastAPI(title='AFC03 Scanner',version='0.3.1')
lock=threading.RLock();processes={};preview_cache={}
LIVE_ACTIVE=('queued','running','waiting','stopping')

def live_state(p):
    with lock:
        state=read(p/'live.json'); proc=processes.get(p.name)
        if state['status'] in LIVE_ACTIVE and (proc is None or proc.poll() is not None):
            state.update(status='interrupted',stage='ended',expected_actions=[],stop_verified=False,error='Worker interrupted; inspect motor before starting another session.')
            t=p/'live.tmp';t.write_text(json.dumps(state));t.replace(p/'live.json')
        if (p/'operator_annotation.json').exists():
            note=read(p/'operator_annotation.json');state.update(title=note.get('title',state['title']))
        return state

def active_live():
    return [s for p in JOBS.glob('live-*') if (p/'live.json').exists() and (s:=live_state(p))['status'] in LIVE_ACTIVE]

def other_work():
    return bool(active_live()) or any(job_state(p)['status'] in ('queued','running') for p in JOBS.iterdir() if (p/'job.json').exists())

def live_path(identifier):
    p=JOBS/valid_id(identifier)
    if not (p/'live.json').exists():raise HTTPException(404,'Scan not found')
    return p

def read(path):return json.loads(path.read_text(encoding='utf-8'))
def valid_id(value):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,90}',value):raise HTTPException(400,'Invalid identifier')
    return value
def dataset_path(identifier):
    path=DATA/valid_id(identifier)
    if not (path/'manifest.json').is_file():raise HTTPException(404,'Dataset not found')
    return path
def job_path(identifier):
    path=JOBS/valid_id(identifier)
    if not (path/'job.json').is_file():raise HTTPException(404,'Job not found')
    return path
def job_state(path):
    state=read(path/'job.json')
    proc=processes.get(path.name)
    if state['status'] in ('queued','running'):
        if (proc is not None and proc.poll() is not None) or (proc is None and state.get('server_pid')!=os.getpid()):
            state.update(status='interrupted',stage='interrupted',error='Service or worker stopped; no automatic replay.')
            temp=path/'job.tmp';temp.write_text(json.dumps(state));temp.replace(path/'job.json')
    return state

@app.middleware('http')
async def local_write_guard(request:Request,call_next):
    if request.method in ('POST','PUT','DELETE','PATCH'):
        origin=request.headers.get('origin')
        if origin and urlsplit(origin).netloc!=request.headers.get('host'):
            return JSONResponse({'detail':'Cross-origin writes are not allowed'},status_code=403)
    return await call_next(request)

@app.get('/api/status')
def status():
    camera={'online':False}
    try:
        camera=json.loads(urllib.request.urlopen(CAMERA_URL+'/status',timeout=.8).read())
        camera['online']=camera.get('age',999)<2
    except Exception:pass
    mem={line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
    return {'version':'0.3.1','mode':'live_and_offline','host':'RK3576','camera':camera,'active_calibrations':calibrations.active(),
            'memory_available_mib':round(mem['MemAvailable']/1024),'motion_control_enabled':True,'active_scans':active_live(),
            'controller_available':Path('/run/afc03-controller/control.sock').is_socket(),
            'serial_present':Path('/run/afc03-controller/control.sock').is_socket(),
            'active_jobs':[j for p in JOBS.iterdir() if p.is_dir() and (p/'job.json').exists() and (j:=job_state(p))['status'] in ('queued','running')]}

@app.get('/api/camera/snapshot')
def snapshot():
    try:data=urllib.request.urlopen(CAMERA_URL+'/snapshot.jpg',timeout=2).read()
    except Exception:raise HTTPException(503,'Camera unavailable')
    im=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
    if im is None:raise HTTPException(503,'Camera returned an invalid image')
    ok,encoded=cv2.imencode('.jpg',cv2.rotate(im,cv2.ROTATE_90_CLOCKWISE),[cv2.IMWRITE_JPEG_QUALITY,85])
    if not ok:raise HTTPException(503,'Preview conversion failed')
    data=encoded.tobytes()
    return Response(data,media_type='image/jpeg',headers={'Cache-Control':'no-store'})


@app.get('/api/diagnostics/latest')
def diagnostics_latest():
    p=ROOT/'diagnostics'/'latest.json'
    if not p.exists():raise HTTPException(404,'No acquisition diagnostic yet')
    return read(p)

@app.get('/api/datasets')
def datasets():return [read(p/'manifest.json') for p in sorted(DATA.iterdir()) if (p/'manifest.json').is_file()]

@app.get('/api/datasets/{identifier}/preview')
def preview(identifier:str):
    p=dataset_path(identifier)
    if identifier not in preview_cache:
        path=p/'colored_cloud_arrays.npz'
        if not path.exists():path=p/'fine_cloud_arrays.npz'
        with np.load(path) as cloud:
            xyz=cloud['display_axis_frame_mm'];rgb=cloud['rgb'];step=max(1,int(np.ceil(len(xyz)/24000)))
            preview_cache[identifier]={'positions':np.round(xyz[::step],3).ravel().tolist(),'colors':rgb[::step].astype(int).ravel().tolist(),
                'full_count':len(xyz),'preview_count':len(xyz[::step]),'units':'mm','real_color':path.name.startswith('colored')}
    return preview_cache[identifier]

ALLOWED={'pointcloud':'fine_360_colored_pointcloud.ply','mesh':'fine_body_colored_mesh.ply','geometry':'fine_360_pointcloud.ply','summary':'fine_summary.json'}
@app.get('/api/datasets/{identifier}/files/{kind}')
def download(identifier:str,kind:str):
    if kind not in ALLOWED:raise HTTPException(404)
    p=dataset_path(identifier)/ALLOWED[kind]
    if not p.is_file():raise HTTPException(404)
    return FileResponse(p,filename=p.name)

class Rebuild(BaseModel):dataset_id:str
@app.post('/api/rebuild',status_code=202)
def rebuild(body:Rebuild):
    p=dataset_path(body.dataset_id)
    if not read(p/'manifest.json').get('rebuild_available'):raise HTTPException(409,'Dataset has no complete raw acquisition')
    with lock:
        if calibrations.active():raise HTTPException(409,'标定正在占用设备')
        if active_live():raise HTTPException(409,'A scan is active')
        for path in JOBS.iterdir():
            if (path/'job.json').exists() and job_state(path)['status'] in ('queued','running'):raise HTTPException(409,'An offline reconstruction is already running')
        if os.statvfs(ROOT).f_bavail*os.statvfs(ROOT).f_frsize<300*1024**2:raise HTTPException(507,'Not enough free storage')
        identifier=uuid.uuid4().hex;job=JOBS/identifier;job.mkdir()
        state={'id':identifier,'dataset_id':body.dataset_id,'status':'queued','stage':'queued','progress':0,'created_unix':time.time(),'server_pid':os.getpid()}
        (job/'job.json').write_text(json.dumps(state))
        with (job/'worker.log').open('wb') as log:
            proc=subprocess.Popen([sys.executable,str(ROOT/'backend/worker.py'),'--dataset',str(p),'--job',str(job)],stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
        processes[identifier]=proc
        return state

@app.get('/api/jobs')
def jobs():return sorted([job_state(p) for p in JOBS.iterdir() if (p/'job.json').exists()],key=lambda x:x['created_unix'],reverse=True)
@app.get('/api/jobs/{identifier}')
def job(identifier:str):return job_state(job_path(identifier))
@app.get('/api/jobs/{identifier}/files/{kind}')
def job_download(identifier:str,kind:str):
    p=job_path(identifier)
    choices={'validation':p/'validation.json','pointcloud':p/'output/fine_360_pointcloud.ply','mesh':p/'output/fine_body_open_mesh.ply','log':p/'worker.log'}
    if kind not in choices or not choices[kind].is_file():raise HTTPException(404)
    return FileResponse(choices[kind],filename=choices[kind].name)

class NewScan(BaseModel):
    title:str=Field(min_length=1,max_length=80)
    fixed:bool
    calibration_unchanged:bool
    laser_off:bool
    roi:tuple[int,int,int,int]=(110,230,970,1030)
    @model_validator(mode='after')
    def validate_ready(self):
        if not (self.fixed and self.calibration_unchanged and self.laser_off):raise ValueError('固定、标定未移动和激光关闭均需确认')
        x0,y0,x1,y1=self.roi
        if not (0<=x0<x1<=1080 and 0<=y0<y1<=1920 and x1-x0>=30 and y1-y0>=50):raise ValueError('Invalid full-frame ROI')
        return self

@app.get('/api/scans')
def scans():return sorted([live_state(p) for p in JOBS.glob('live-*') if (p/'live.json').exists()],key=lambda s:s['created_unix'],reverse=True)

@app.post('/api/scans',status_code=202)
def start_scan(body:NewScan):
    with lock:
        if calibrations.active():raise HTTPException(409,'请先结束标定任务')
        if active_live():raise HTTPException(409,'已有扫描正在运行')
        if any(job_state(p)['status'] in ('queued','running') for p in JOBS.iterdir() if (p/'job.json').exists()):raise HTTPException(409,'离线重建正在运行')
        if shutil.disk_usage(JOBS).free<1500*1024**2:raise HTTPException(507,'至少需要 1.5 GiB 可用空间')
        identifier='live-'+uuid.uuid4().hex;p=JOBS/identifier;p.mkdir()
        bundle=calibrations.active_bundle()
        cfg={'intervals':180,'repeat_filter_px':3,'step_pulses':[round(i*3200/180)-round((i-1)*3200/180) for i in range(1,181)],'roi':body.roi,'gain_geometry':10,'gain_color':70,'led_geometry':0,'led_color':8,'operator_confirmation':body.model_dump(),'calibration':'provisional','calibration_version':bundle.name,'software_version':'0.3.1'}
        (p/'scan_config.json').write_text(json.dumps(cfg,ensure_ascii=False),encoding='utf-8')
        for name in ['laser_plane_v2_provisional.json','turntable_axis_v1_provisional.json']:
            shutil.copy2(bundle/name,p/name)
        shutil.copy2(bundle/'version.json',p/'calibration_version.json')
        state={'id':identifier,'title':body.title,'status':'queued','stage':'connecting','created_unix':time.time(),'progress':0,'server_pid':os.getpid(),'expected_actions':[],'roi':body.roi,'real_color':False,'geometry_available':False}
        (p/'live.json').write_text(json.dumps(state,ensure_ascii=False),encoding='utf-8')
        with (p/'worker.log').open('wb') as log:
            try:processes[identifier]=subprocess.Popen([sys.executable,str(ROOT/'backend/live_worker.py'),'--scan',str(p)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
            except Exception:
                state.update(status='failed',stage='ended',error='Could not launch worker');(p/'live.json').write_text(json.dumps(state));raise
        return state

class ScanAction(BaseModel):
    stage:str
    action:str

class ResumeScan(BaseModel):
    unchanged_and_laser_on:bool

@app.post('/api/scans/{identifier}/resume',status_code=202)
def resume_scan(identifier:str,body:ResumeScan):
    with lock:
        if calibrations.active():raise HTTPException(409,'标定正在运行')
        p=live_path(identifier);state=live_state(p)
        if not body.unchanged_and_laser_on:raise HTTPException(422,'需要确认物体和支架未动、激光开启')
        if active_live():raise HTTPException(409,'已有任务正在采集')
        if any(job_state(d)['status'] in ('queued','running') for d in JOBS.iterdir() if (d/'job.json').exists()):raise HTTPException(409,'重建正在运行')
        if state['status']!='failed' or not state.get('stop_verified') or state.get('error')!='Laser stripe unstable between stationary frames':raise HTTPException(409,'该中断不支持经核对继续')
        index=state.get('pending_index')
        if not isinstance(index,int) or not 1<=index<=180 or (p/f'position{index:03d}_record.json').exists():raise HTTPException(409,'无法确定未完成位置')
        motion=read(p/f'position{index:03d}_motion.json')
        if motion.get('status')!='settled':raise HTTPException(409,'未确认转动完成，不能继续')
        archive=p/'attempts'/('state-'+uuid.uuid4().hex);archive.mkdir(parents=True)
        shutil.copy2(p/'live.json',archive/'live.json');shutil.copy2(p/'scan_config.json',archive/'scan_config.json')
        if (p/'stop.request').exists():(p/'stop.request').rename(archive/'stop.request')
        cfg=read(p/'scan_config.json');cfg.update(repeat_filter_px=3,software_version='0.2.1')
        (p/'scan_config.json').write_text(json.dumps(cfg,ensure_ascii=False),encoding='utf-8')
        (p/'resume.json').write_text(json.dumps({'index':index,'operator_unchanged_and_laser_on':True,'policy':'No move at resumed position; verify encoder and scene before re-acquiring'}))
        for key in ['stop_verified','stop_samples','stop_reply','stop_error','error']:state.pop(key,None)
        state.update(status='queued',stage='connecting',expected_actions=[],resume_count=state.get('resume_count',0)+1)
        (p/'live.json').write_text(json.dumps(state,ensure_ascii=False),encoding='utf-8')
        with (p/'worker.log').open('ab') as log:
            processes[identifier]=subprocess.Popen([sys.executable,str(ROOT/'backend/live_worker.py'),'--scan',str(p)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
        return state

@app.post('/api/scans/{identifier}/action',status_code=202)
def scan_action(identifier:str,body:ScanAction):
    with lock:
        p=live_path(identifier);s=live_state(p)
        if s['status']!='waiting' or s['stage']!=body.stage or body.action not in s.get('expected_actions',[]):raise HTTPException(409,'状态已改变，请刷新后确认')
        if (p/'stop.request').exists() or (p/'action.request').exists():raise HTTPException(409,'已有操作待处理')
        tmp=p/'action.tmp';tmp.write_text(body.model_dump_json());tmp.replace(p/'action.request')
        return {'accepted':True,'meaning':'Worker will validate position before continuing'}

@app.post('/api/scans/{identifier}/stop',status_code=202)
def scan_stop(identifier:str):
    with lock:
        p=live_path(identifier);s=live_state(p)
        if s['status'] not in LIVE_ACTIVE:raise HTTPException(409,'No active worker; stop is not verified by this request')
        (p/'stop.request').touch()
        return {'accepted':True,'stop_verified':False,'meaning':'Await encoder feedback; this response only queues STOP'}

@app.get('/api/scans/{identifier}/preview')
def scan_preview(identifier:str):
    p=live_path(identifier);s=live_state(p)
    if not s.get('geometry_available'):raise HTTPException(409,'Geometry is not ready')
    file=p/('colored_cloud_arrays.npz' if s.get('real_color') else 'fine_cloud_arrays.npz')
    with np.load(file) as cloud:
        xyz=cloud['display_axis_frame_mm'];rgb=cloud['rgb'];step=max(1,int(np.ceil(len(xyz)/24000)))
        return {'positions':np.round(xyz[::step],3).ravel().tolist(),'colors':rgb[::step].astype(int).ravel().tolist(),'full_count':len(xyz),'preview_count':len(xyz[::step]),'units':'mm','real_color':bool(s.get('real_color'))}

@app.get('/api/scans/{identifier}/files/{kind}')
def scan_download(identifier:str,kind:str):
    p=live_path(identifier);s=live_state(p)
    choices={'timing':'timing_summary.json','audit':'completion_verification.json','archive':'result_archive.zip','manifest':'archive_manifest.json','summary':'fine_summary.json','log':'worker.log','config':'scan_config.json','pointcloud':'fine_360_colored_pointcloud.ply' if s.get('real_color') else 'fine_360_pointcloud.ply','mesh':'fine_body_colored_mesh.ply' if s.get('real_color') else 'fine_body_open_mesh.ply'}
    if kind not in choices or not (p/choices[kind]).is_file():raise HTTPException(404)
    if kind in ('mesh','pointcloud','summary') and not s.get('geometry_available'):raise HTTPException(409)
    return FileResponse(p/choices[kind],filename=choices[kind])

from .calibration_api import Calibrations,register
calibrations=Calibrations(ROOT,lock,processes,other_work)
register(app,calibrations)
from .fpga_api import install as install_fpga_api
install_fpga_api(app, ROOT)
from .surface_api import install as install_surface_api
install_surface_api(app, ROOT, lock, lambda: other_work() or bool(calibrations.active()))
from scan3d.api import install as install_scan3d_api
install_scan3d_api(app, ROOT)
app.mount('/',StaticFiles(directory=ROOT/'frontend/dist',html=True),name='frontend')
