import sys
sys.path[:0]=['/opt/afc03-scanner/scan3d','/opt/afc03-scanner/fpga','/opt/afc03-motor']
"""One explicit 360-degree scan, no restart/resume or motion command replay."""
import argparse,fcntl,hashlib,json,os,pwd,shutil,signal,time
from pathlib import Path
import cv2,numpy as np
from stationary_strategy import acquire,motor_state,write,PORT,ROOT
from motion import move_once
from row_results import require
from rk_motor import MotorBridge
from scan_storage import write_ply
from scan_pipeline import ScanPipeline
from image_retention import policy as image_policy, SampledStorage, keep as keep_image
from scan_tuning import settings,full_pixel_check
from spatial_filter import validate as spatial_validate
from preview_gain import PreviewGain
from rk_candidate_policy import VERSION
from storage_budget import projection as storage_projection, failure_message as storage_failure

def merge(output,indices):
    combined=[];colors=[];summary={};provenance=[]
    for label in ('A','B'):
        xyz=[];rgb=[]
        for index in indices:
            with np.load(output/f'position-{index:03d}'/label/'points.npz',allow_pickle=False) as f:
                xyz.append(f['axis_frame_mm']);rgb.append(f['rgb']);provenance.append(dict(xyz=f['axis_frame_mm'],rgb=f['rgb'],scheme2=f['scheme2'],long_track_suspect=f['long_track_suspect'] if 'long_track_suspect' in f.files else np.zeros(len(f['uv']),np.uint8),ground_branch=f['ground_branch'] if 'ground_branch' in f.files else np.zeros(len(f['uv']),np.uint8),saturated=f['saturated'],adaptive_origin=f['adaptive_origin'] if 'adaptive_origin' in f.files else np.zeros(len(f['uv']),np.uint8),threshold=f['threshold'] if 'threshold' in f.files else np.full(len(f['uv']),40,np.uint8),position=np.full(len(f['uv']),index,np.uint16),laser=np.full(len(f['uv']),0 if label=='A' else 1,np.uint8)))
        xyz=np.concatenate(xyz);rgb=np.concatenate(rgb)
        target=output/label;target.mkdir(exist_ok=True)
        np.savez_compressed(target/'points.npz',axis_frame_mm=xyz,rgb=rgb)
        write_ply(target/'points.ply',xyz,rgb)
        combined.append(xyz);colors.append(rgb);summary[label]=len(xyz)
    write_ply(output/'combined-color.ply',np.concatenate(combined),np.concatenate(colors))
    merged={k:np.concatenate([r[k] for r in provenance]) for k in provenance[0]};merged['inferred']=np.zeros(len(merged['xyz']),np.uint8);np.savez_compressed(output/'combined.npz',**merged)
    return summary

def closure(output):
    from manual_color_round import appearance_check
    cfg=json.loads((output/'bundle/config.json').read_text())
    images=[cv2.rotate(cv2.imread(str(output/f'position-{i:03d}/COLOR/same-frame.png')),cv2.ROTATE_90_CLOCKWISE) for i in (0,INTERVALS)]
    return appearance_check(*images,cfg['scan_roi'],limit=3.)

from chat_priority import priority_operation

@priority_operation
def run(output,resume=False,data_root=Path('/userdata/afc03-scanner/jobs'),timing_profile=None):
    tuning=settings(timing_profile)
    require(output.parent.resolve()==data_root.resolve(),'Full scan must use data partition')
    if resume:
        state=json.loads((output/'status.json').read_text())
        cfg=json.loads((output/'bundle/config.json').read_text())
        rules=state['image_retention'];empty=0;sizes=[]
        start=time.perf_counter()-state.get('elapsed_seconds',0)
    else:
        output.mkdir(exist_ok=False)
        user=pwd.getpwnam('afcscanner');os.chown(output,user.pw_uid,user.pw_gid)
        shutil.copytree(ROOT/'new-strategy-bundle',output/'bundle')
        spatial_path=data_root/'scan3d-work/spatial-profile.json'
        if spatial_path.exists():
            spatial=spatial_validate(json.loads(spatial_path.read_text(encoding='utf-8')))
            spatial['axis_sha256']=hashlib.sha256((output/'bundle/axis.json').read_bytes()).hexdigest()
            write(output/'bundle/spatial_filter.json',spatial)
        cfg=json.loads((output/'bundle/config.json').read_text());cfg.update(intervals=INTERVALS,requested_step_deg=STEP,profile=VERSION,object_name=TITLE,angle_schedule=[round(i*3200/INTERVALS) for i in range(INTERVALS+1)],final_extraction='pending-hardware-version');write(output/'bundle/config.json',cfg)
        state=dict(status='running',mode='scan3d',object_name=TITLE,final_extraction='pending-hardware-version',phase='preflight',pid=os.getpid(),
            boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),passed=False,
            points_are_static_profile=False,absolute_accuracy_validated=False,
            planned_intervals=INTERVALS,commanded_step_deg=STEP,requested_step_deg=STEP,angle_schedule=[round(i*3200/INTERVALS) for i in range(INTERVALS+1)],last_index=-1,lasers={},
            completed_positions=0,capture_retries=0,retained_points={'A':0,'B':0},
            angle_source='commanded_pulses_no_encoder',automatic_resume=False)
        rules=image_policy(STEP,INTERVALS)
        cfg['image_retention']=rules;write(output/'bundle/config.json',cfg)
        state['image_retention']=rules
        state['title']=TITLE;state['timing_profile']=tuning;state['stage_seconds']={}
        start=time.perf_counter();state['started_monotonic']=time.monotonic();write(output/'status.json',state);empty=0;sizes=[]
    def check():
        pipeline.check()
        require(not (output/'STOP').exists(),'Operator stop requested')
        require(shutil.disk_usage(output).free>1024**3,'Data partition below 1 GiB reserve')
    pipeline=ScanPipeline(capacity=2,store=SampledStorage(rules))
    retained_sizes=[];sampled_sizes=[]
    def consume(done):
        nonlocal empty
        if done is None:return
        folder=done['folder'];index=int(folder.name.split('-')[-1]);report=done['report']
        for label in ('A','B'):
            header=json.loads((folder/label/'frame.json').read_text())
            require(header['angle']['emitted_after']==origin+round(index*3200/INTERVALS),'Capture angle mismatch')
            state['retained_points'][label]+=report['lasers'][label]['retained_points']
        if index==0:
            versions={r['strategy']['version'] for r in report['lasers'].values()}
            require(len(versions)==1,'A/B strategy versions differ')
            state['final_extraction']=next(iter(versions))
            cfg['final_extraction']=state['final_extraction'];cfg['stripe_settings']=report['lasers']['A']['strategy']['stripe_settings'];write(output/'bundle/config.json',cfg)
            require(report['scan_ready'],'Initial dual-laser point count below minimum')
            require(60<report['color']['median_max']<245 and report['color']['saturated_fraction']<.15,
                    'Initial colour exposure needs adjustment; no motor movement issued')
        total=sum(x['retained_points'] for x in report['lasers'].values())
        empty=empty+1 if total<10 else 0
        require(empty<10,'Both profiles lost for 10 consecutive positions')
        sizes.append(done['stored_bytes'])
        (retained_sizes if keep_image(index,rules) else sampled_sizes).append(done['stored_bytes'])
        if not sampled_sizes:
            from image_retention import frame_paths
            sampled_sizes.append(max(0,done['stored_bytes']-sum(p.stat().st_size for p in frame_paths(folder))))
        for f in folder.glob('*/report.json'):
            r=json.loads(f.read_text());state['capture_retries']+=max(0,r.get('capture_attempts',1)-1)
        state.update(last_index=index,completed_positions=index+1,lasers=report['lasers'],color=report['color'],
            commanded_degrees=round(index*3200/INTERVALS)*.1125,elapsed_seconds=time.perf_counter()-start,
            stored_bytes=sum(sizes),mean_position_seconds=(time.perf_counter()-start)/(index+1))
        state['estimated_remaining_seconds']=(INTERVALS-index)*state['mean_position_seconds']
        state['pipeline']=dict(capacity=pipeline.capacity,high_water=pipeline.high_water,pending=len(pipeline.pending),last_storage_seconds=done['storage_seconds'])
        state['storage_projection']=storage_projection(shutil.disk_usage(output).free,sizes,INTERVALS-index,
            retained_sizes=retained_sizes,sampled_sizes=sampled_sizes,
            remaining_retained=sum(keep_image(i,rules) for i in range(index+1,INTERVALS+1)))
        write(output/'status.json',state)
        print(json.dumps({k:state[k] for k in ('last_index','commanded_degrees','elapsed_seconds','capture_retries')}),flush=True)
        require(state['storage_projection']['sufficient'],storage_failure(state['storage_projection']))
    lock=None;preview_gain=None;hardware_owned=False
    try:
        lock=open('/run/lock/afc03-fpga-scan.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if resume:
            from scan_resume import plan_resume
            probe=MotorBridge(PORT)
            try:plan_resume(output,state,motor_state(probe),Path('/proc/sys/kernel/random/boot_id').read_text().strip())
            finally:probe.close()
        hardware_owned=True
        preview_gain=PreviewGain()
        state['preview_gain']=dict(device=preview_gain.device,saved=preview_gain.value,verified=False)
        require(shutil.disk_usage(output).free>3*1024**3,'Insufficient startup storage')
        b=MotorBridge(PORT)
        try:
            initial=motor_state(b);b.send('LASER OFF');b.send('LED 0')
            b.send('PULSE_ARM '+str(initial['session']));b.send('PULSE_DISARM');time.sleep(.6)
            held=motor_state(b);require(held['session']==initial['session'] and held['emitted']==initial['emitted'],'State changed during hold setup');initial=held
        finally:b.close()
        first=0;skip_first_move=False
        if resume:
            from scan_resume import plan_resume
            plan=plan_resume(output,state,initial,Path('/proc/sys/kernel/random/boot_id').read_text().strip())
            origin=plan['origin'];session=plan['session'];first=plan['start'];skip_first_move=plan['skip_move']
            audit=output/'resume-audit'/str(time.time_ns());audit.mkdir(parents=True)
            shutil.copy2(output/'status.json',audit/'status-before.json')
            for folder in output.glob('position-*'):
                if int(folder.name.split('-')[-1])>=first:folder.rename(audit/folder.name)
            if (output/'STOP').exists():(output/'STOP').rename(audit/'STOP')
            state.update(status='running',phase='resuming',pid=os.getpid(),last_index=first-1,completed_positions=first,retained_points=plan['counts'])
            state.pop('error',None);sizes.extend(plan['sizes'])
            write(output/'status.json',state)
        else:
            origin=initial['emitted'];session=initial['session'];state['initial_motor']=initial
        for index in range(first,INTERVALS+1):
            check()
            while len(pipeline.pending)>=pipeline.capacity:consume(pipeline.retire(wait=True))
            while pipeline.pending and pipeline.pending[0]['stored'].done():consume(pipeline.retire())
            if index and not (resume and index==first and skip_first_move):
                state['phase']='moving';state['target_index']=index;write(output/'status.json',state)
                b=MotorBridge(PORT)
                try:
                    before=motor_state(b)
                    expected_before=plan['current'] if resume and index==first else origin+round((index-1)*3200/INTERVALS)
                    require(before['session']==session and before['emitted']==expected_before,'Motor session/position changed')
                    move_once(b,before,origin+round(index*3200/INTERVALS)-before['emitted'],tuning['rate_pps'],output/f'move-{index:03d}-resume-{time.time_ns()}.json' if resume and index==first else output/f'move-{index:03d}.json',check)
                finally:b.close()
                time.sleep(tuning['motor_settle'])
            state['phase']='acquiring';write(output/'status.json',state)
            folder=output/f'position-{index:03d}'
            report=acquire(folder,output/'bundle',False,zero_pulses=origin,
                expected_motor=dict(session=session,emitted=origin+round(index*3200/INTERVALS)),
                external_check=check,scan_lock_owned=True,color_led=8,pipeline=pipeline,
                timing_profile=tuning['name'],verify_pixels=full_pixel_check(tuning,index,INTERVALS))
            if index==0:consume(pipeline.retire(wait=True))
            while pipeline.pending and pipeline.pending[0]['stored'].done():consume(pipeline.retire())
        while pipeline.pending:consume(pipeline.retire(wait=True))
        state['phase']='closure_check';write(output/'status.json',state);t=time.perf_counter()
        state['closure']=closure(output);state['stage_seconds']['closure']=time.perf_counter()-t;write(output/'status.json',state)
        require(state['closure']['passed'],'Full-turn image closure failed; retain all data for review')
        state['phase']='merging';write(output/'status.json',state)
        # 360 degree frame is validation only, not duplicated in the model.
        t=time.perf_counter();state['model_points']=merge(output,range(INTERVALS));state['stage_seconds']['merge']=time.perf_counter()-t
        state.update(status='complete',phase='complete',passed=True,
            scan_ready=False,scan_ready_scope='Full acquisition and closure passed; dimensional accuracy remains unvalidated')
    except BaseException as e:
        if resume and not hardware_owned:raise
        state.update(status='paused',phase='stopped',error=type(e).__name__+': '+str(e),passed=False)
        raise
    finally:
        if hardware_owned:
            try:
                b=MotorBridge(PORT)
                try:
                    b.send('STOP');b.send('LASER OFF');b.send('LED 0');state['final_motor']=motor_state(b)
                finally:b.close()
            except Exception as e:state['cleanup_error']=str(e);state.update(status='paused',passed=False)
        try:pipeline.close()
        except Exception as e:
            state['pipeline_error']=str(e);state.update(status='paused',passed=False)
        if preview_gain is not None:
            try:state['preview_gain']=preview_gain.restore()
            except Exception as e:
                state['preview_gain_restore_error']=str(e);state.update(status='paused',passed=False)
        try:
            if not resume or hardware_owned:
                state['elapsed_seconds']=time.perf_counter()-start;write(output/'status.json',state)
        finally:
            if lock is not None:lock.close()
        # Keep a clearly labelled review model even if final closure rejects it.
        if hardware_owned and state.get('last_index')==INTERVALS and not state.get('passed'):
            try:
                state['review_pending_offline']=True;write(output/'status.json',state)
            except Exception as e:
                state['review_error']=str(e);write(output/'status.json',state)
    return state

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--request',type=Path,required=True);p.add_argument('--mode',choices=['scan','capture'],required=True);p.add_argument('--resume',action='store_true');a=p.parse_args()
 config=json.loads(a.request.read_text());STEP=config['step'];TITLE=config['title'];INTERVALS=round(360/STEP)
 require(STEP in (.1125,.45,2,6),'Invalid step');cv2.setNumThreads(2)
 signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(KeyboardInterrupt()))
 if a.mode=='scan':run(a.output,resume=a.resume,timing_profile='fast')
 else:
  from scan_storage import compress_position
  a.output.mkdir();shutil.copytree(ROOT/'new-strategy-bundle',a.output/'bundle')
  spatial_path=a.output.parent/'scan3d-work/spatial-profile.json'
  if spatial_path.exists():
   spatial=spatial_validate(json.loads(spatial_path.read_text(encoding='utf-8')))
   spatial['axis_sha256']=hashlib.sha256((a.output/'bundle/axis.json').read_bytes()).hexdigest()
   write(a.output/'bundle/spatial_filter.json',spatial)
  state=dict(status='running',title=TITLE,mode='stationary',pid=os.getpid(),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),completed_positions=0)
  write(a.output/'status.json',state)
  try:
   acquire(a.output/'position-000',a.output/'bundle',False,color_led=8,timing_profile='fast')
   compress_position(a.output/'position-000');state.update(status='complete',completed_positions=1,last_index=0,passed=True,scope='stationary capture only; not full turn')
  except BaseException as e:state.update(status='failed',error=str(e));raise
  finally:write(a.output/'status.json',state)
