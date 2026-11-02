"""Read-only FPGA run visibility. No privileged register or motion API."""
import json,os,re
from pathlib import Path
import numpy as np
from fastapi import HTTPException
from fastapi.responses import FileResponse,JSONResponse

def install(app,root):
    jobs=root/'jobs'
    def runs():
        records=[]
        for p in sorted([*jobs.glob('fpga-static-*'),*jobs.glob('fpga-pilot-*'),*jobs.glob('fpga-full-*')],
                        key=lambda p:p.name.split('-',2)[2],reverse=True)[:30]:
            if not (p/'status.json').is_file():continue
            try:r=json.loads((p/'status.json').read_text())
            except (ValueError,OSError):continue
            r['id']=p.name;records.append(r)
        return records
    @app.middleware('http')
    async def exclusive_capture(request,call_next):
        is_stop=re.fullmatch(r'/api/fpga/runs/fpga-full-[0-9]{8}-[0-9]{6}/stop',request.url.path)
        if request.method in ('POST','PUT','DELETE','PATCH') and not is_stop:
            boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            for r in runs():
                if r.get('status')=='running' and r.get('boot_id')==boot:
                    cmd=Path('/proc')/str(r.get('pid',-1))/'cmdline'
                    try:
                        command=cmd.read_bytes()
                        alive=any(('/opt/afc03-scanner/fpga/'+name).encode() in command for name in ('stationary.py','pilot.py','full_scan.py','strategy_coarse6.py','stationary_strategy.py','strategy_scan.py','stationary_strategy.py'))
                    except OSError:alive=False
                    if alive:return JSONResponse({'detail':'FPGA 采集正在占用设备，请等待完成。'},status_code=409)
        return await call_next(request)
    @app.get('/api/fpga/status')
    def status():
        p=Path('/run/afc03-fpga-ready.json')
        ready=json.loads(p.read_text()) if p.exists() else {'passed':False}
        return dict(ddr=ready,runs=runs(),mode='static_and_finite_pilot',web_motion_enabled=False,
                    complete_scan_verified=False,cold_boot_verified=False)
    @app.get('/api/fpga/runs/{identifier}/points')
    def points(identifier:str):
        if not re.fullmatch(r'fpga-(static|pilot|full)-[0-9]{8}-[0-9]{6}',identifier):raise HTTPException(400,'Invalid run')
        path=jobs/identifier
        if not (path/'status.json').is_file():raise HTTPException(404)
        state=json.loads((path/'status.json').read_text())
        accepted=bool(state.get('passed') and state.get('status')=='complete')
        review=bool(state.get('review_ready') and state.get('status')!='running')
        if not accepted and not review:raise HTTPException(409,'Incomplete run')
        if not accepted:path=path/'review'
        result={};colors={}
        for label in ('A','B'):
            with np.load(path/label/'points.npz',allow_pickle=False) as a:
                stride=max(1,(len(a['axis_frame_mm'])+24999)//25000)
                result[label]=np.round(a['axis_frame_mm'][::stride],4).tolist()
                if 'rgb' in a:colors[label]=a['rgb'][::stride].tolist()
        return dict(units='mm',static_profiles=state.get('points_are_static_profile',True),
                    physical_motion_verified=state.get('physical_motion_verified',False),
                    accepted=accepted,absolute_accuracy_validated=False,points=result,colors=colors,preview_may_be_subsampled=True)
    @app.post('/api/fpga/runs/{identifier}/stop')
    def stop(identifier:str):
        if not re.fullmatch(r'fpga-full-[0-9]{8}-[0-9]{6}',identifier):raise HTTPException(400,'Invalid run')
        path=jobs/identifier
        if not (path/'status.json').is_file():raise HTTPException(404)
        try:
            with (path/'STOP').open('x'):pass
        except FileExistsError:pass
        return {'stop_requested':True}
    @app.get('/api/fpga/runs/{identifier}/model')
    def model(identifier:str):
        if not re.fullmatch(r'fpga-full-[0-9]{8}-[0-9]{6}',identifier):raise HTTPException(400,'Invalid run')
        path=jobs/identifier
        if not (path/'status.json').is_file():raise HTTPException(404)
        state=json.loads((path/'status.json').read_text())
        if not state.get('passed') or state.get('status')!='complete':raise HTTPException(409,'Model not accepted')
        return FileResponse(path/'combined-color.ply',filename=identifier+'-color.ply')
    @app.get('/fpga')
    def page():return FileResponse(root/'frontend/fpga.html')
    @app.get('/api/fpga/runs/{identifier}/review-model')
    def review_model(identifier:str):
        if not re.fullmatch(r'fpga-full-[0-9]{8}-[0-9]{6}',identifier):raise HTTPException(400,'Invalid run')
        path=jobs/identifier
        if not (path/'status.json').is_file():raise HTTPException(404)
        state=json.loads((path/'status.json').read_text())
        if not state.get('review_ready') or state.get('status')=='running':raise HTTPException(409,'Review unavailable')
        return FileResponse(path/'review/UNVALIDATED-color.ply',filename=identifier+'-UNVALIDATED-color.ply')
