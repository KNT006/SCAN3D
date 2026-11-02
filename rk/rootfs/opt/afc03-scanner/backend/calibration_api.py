"""Calibration API and immutable parameter bundles stored under jobs/."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Literal
import uuid
from fastapi import HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field
from .calibration_math import digest,read
from .live_geometry import write_json

class NewCalibration(BaseModel):
    kind:Literal['camera','laser','axis']
    title:str=Field(min_length=1,max_length=80)
    pattern:tuple[int,int]=(8,6)
    square_mm:float=Field(default=11,gt=0,le=100)
    camera_source:str='legacy'
    laser_off:bool
    rigid_board:bool
class Command(BaseModel):
    token:str
    action:Literal['capture','move','solve','finish','discard_pose']
    stage:Literal['pattern','background','laser_on']='pattern'
    held_out:bool=False
    laser_on:bool=False
    stationary_confirmed:bool=False
class Bundle(BaseModel):
    camera:str
    laser:str
    axis:str
    confirmed:bool
class Activate(BaseModel):confirmed:bool

class Calibrations:
    def __init__(self,root,lock,processes,busy):
        self.root=root;self.base=root/'jobs/calibrations';self.base.mkdir(exist_ok=True)
        self.versions=self.base/'versions';self.versions.mkdir(exist_ok=True)
        self.lock=lock;self.processes=processes;self.busy=busy
        legacy=self.versions/'legacy'
        if not legacy.exists():
            temporary=self.versions/('seed-'+uuid.uuid4().hex);temporary.mkdir()
            for name in ['laser_plane_v2_provisional.json','turntable_axis_v1_provisional.json']:shutil.copy2(root/'data/fine-20260927'/name,temporary/name)
            write_json(temporary/'camera.json',read(temporary/'laser_plane_v2_provisional.json')['camera'])
            write_json(temporary/'version.json',dict(id='legacy',title='现用临时标定（保留原参数）',provisional=True,absolute_accuracy_validated=False,camera_sha256=digest(temporary/'camera.json')))
            temporary.rename(legacy)
        if not (self.base/'active.json').exists():write_json(self.base/'active.json',{'id':'legacy'})
    def path(self,ident):
        import re
        if not re.fullmatch('cal-[a-f0-9]{32}',ident):raise HTTPException(404,'无效标定编号')
        p=self.base/ident
        if not (p/'live.json').exists():raise HTTPException(404,'标定不存在')
        return p
    def state(self,p):
        s=read(p/'live.json');proc=self.processes.get(p.name)
        if s['status'] in ('queued','waiting','running','stopping') and (proc is None or proc.poll() is not None):
            s.update(status='interrupted',stage='ended',token=None,error='标定进程中断；不自动重放运动。请检查电机。');write_json(p/'live.json',s)
        return s
    def sessions(self):return sorted([self.state(p) for p in self.base.glob('cal-*') if (p/'live.json').exists()],key=lambda x:x['created_unix'],reverse=True)
    def active(self):return [s for s in self.sessions() if s['status'] in ('queued','waiting','running','stopping')]
    def camera(self,source):
        p=self.versions/'legacy/camera.json' if source=='legacy' else self.path(source)/'result.json'
        if not p.exists():raise HTTPException(409,'相机参数尚未计算')
        r=read(p)
        if source!='legacy' and (r.get('kind')!='camera' or not r.get('passed')):raise HTTPException(409,'相机标定未通过检查')
        return p
    def active_bundle(self):
        v=read(self.base/'active.json')['id'];p=self.versions/v
        if p.parent!=self.versions or not (p/'version.json').exists():raise RuntimeError('Active calibration missing')
        return p

def register(app,store):
    @app.get('/api/calibrations')
    def listing():
        with store.lock:
            return dict(sessions=store.sessions(),versions=[read(p/'version.json') for p in store.versions.iterdir() if (p/'version.json').exists()],active=read(store.base/'active.json')['id'])
    @app.post('/api/calibrations',status_code=202)
    def create(body:NewCalibration):
        with store.lock:
            if store.busy() or store.active():raise HTTPException(409,'扫描、重建或标定正在占用设备')
            if not body.laser_off or not body.rigid_board:raise HTTPException(422,'请确认激光关闭、棋盘格贴平并固定')
            if not all(3<=i<=20 for i in body.pattern):raise HTTPException(422,'角点数量范围为 3–20')
            source=store.camera(body.camera_source) if body.kind!='camera' else None
            if shutil.disk_usage(store.base).free<500*1024**2:raise HTTPException(507,'标定至少需要 500 MiB 空间')
            ident='cal-'+uuid.uuid4().hex;p=store.base/ident;p.mkdir()
            cfg=body.model_dump();cfg['source']='live_camera';write_json(p/'scan_config.json',cfg)
            if source:shutil.copy2(source,p/'camera.json')
            write_json(p/'captures.json',[])
            s=dict(id=ident,title=body.title,kind=body.kind,status='queued',stage='connecting',created_unix=time.time(),captures=0,training=0,held_out=0,next_stage='pattern',pattern=body.pattern,square_mm=body.square_mm,camera_source=body.camera_source)
            write_json(p/'live.json',s)
            with (p/'worker.log').open('wb') as log:
                try:store.processes[ident]=subprocess.Popen([sys.executable,str(store.root/'backend/calibration_worker.py'),'--session',str(p)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
                except Exception:
                    s.update(status='failed',error='无法启动标定进程');write_json(p/'live.json',s);raise
            return s
    @app.post('/api/calibrations/{ident}/command',status_code=202)
    def command(ident:str,body:Command):
        with store.lock:
            p=store.path(ident);s=store.state(p)
            if s['status']!='waiting' or body.token!=s.get('token'):raise HTTPException(409,'状态已变化，请刷新')
            if (p/'action.request').exists() or (p/'stop.request').exists():raise HTTPException(409,'已有操作等待执行')
            if body.action in ('capture','move') and not body.stationary_confirmed:raise HTTPException(422,'需确认物体和支架固定、激光状态正确')
            if body.action=='move' and (s['kind']!='axis' or body.laser_on):raise HTTPException(422,'仅支持激光关闭时转轴标定点动')
            write_json(p/'action.request',body.model_dump());return {'accepted':True}
    @app.post('/api/calibrations/{ident}/stop',status_code=202)
    def stop(ident:str):
        with store.lock:
            p=store.path(ident);s=store.state(p)
            if s['status'] not in ('queued','waiting','running','stopping'):raise HTTPException(409,'标定未运行')
            (p/'stop.request').touch();return {'accepted':True,'stop_verified':False}
    @app.get('/api/calibrations/{ident}/files/{kind}')
    def files(ident:str,kind:str):
        choices={'result':'result.json','captures':'captures.json','preview':'corners.jpg','config':'scan_config.json','log':'worker.log'}
        p=store.path(ident)
        if kind not in choices or not (p/choices[kind]).is_file():raise HTTPException(404)
        return FileResponse(p/choices[kind],filename=choices[kind],headers={'Cache-Control':'no-store'})
    @app.post('/api/calibration-versions')
    def bundle(body:Bundle):
        with store.lock:
            if store.busy() or store.active():raise HTTPException(409,'请先结束当前任务')
            if not body.confirmed:raise HTTPException(422,'请确认标定检查和机械位置')
            cam=store.camera(body.camera);sha=digest(cam);parts={}
            for kind,ident in [('laser',body.laser),('axis',body.axis)]:
                f=store.path(ident)/'result.json'
                if not f.exists():raise HTTPException(409,'标定尚未计算')
                result=read(f)
                if result.get('kind')!=kind or not result.get('passed') or result.get('camera_sha256')!=sha:raise HTTPException(409,'标定未通过，或相机参数版本不一致')
                parts[kind]=f
            ident='v-'+uuid.uuid4().hex;p=store.versions/ident;p.mkdir()
            shutil.copy2(cam,p/'camera.json');shutil.copy2(parts['laser'],p/'laser_plane_v2_provisional.json');shutil.copy2(parts['axis'],p/'turntable_axis_v1_provisional.json')
            metadata=dict(id=ident,title='板端验证标定 '+ident[2:10],sources=body.model_dump(),camera_sha256=sha,provisional=body.camera=='legacy',absolute_accuracy_validated=False)
            write_json(p/'version.json',metadata);write_json(store.base/'active.json',{'id':ident});return metadata
    @app.post('/api/calibration-versions/{ident}/activate')
    def activate(ident:str,body:Activate):
        with store.lock:
            if store.busy() or store.active():raise HTTPException(409,'请先结束当前任务')
            if not body.confirmed:raise HTTPException(422,'需确认机械结构对应此版本')
            versions={p.name for p in store.versions.iterdir() if (p/'version.json').exists()}
            if ident not in versions:raise HTTPException(404)
            write_json(store.base/'active.json',{'id':ident});return {'active':ident}
