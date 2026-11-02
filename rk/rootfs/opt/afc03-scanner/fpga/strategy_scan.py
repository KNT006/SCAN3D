"""One explicit 360-degree scan, no restart/resume or motion command replay."""
import argparse,fcntl,hashlib,json,os,pwd,shutil,signal,time
from pathlib import Path
import cv2,numpy as np
from stationary_strategy import acquire,motor_state,write,PORT,ROOT
from pilot import move_once
from row_results import require
from rk_motor import MotorBridge
from scan_storage import write_ply
from scan_pipeline import ScanPipeline

def merge(output,indices):
    combined=[];colors=[];summary={};provenance=[]
    for label in ('A','B'):
        xyz=[];rgb=[]
        for index in indices:
            with np.load(output/f'position-{index:03d}'/label/'points.npz',allow_pickle=False) as f:
                xyz.append(f['axis_frame_mm']);rgb.append(f['rgb']);provenance.append(dict(xyz=f['axis_frame_mm'],rgb=f['rgb'],scheme2=f['scheme2'],saturated=f['saturated'],position=np.full(len(f['uv']),index,np.uint16),laser=np.full(len(f['uv']),0 if label=='A' else 1,np.uint8)))
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
    images=[cv2.rotate(cv2.imread(str(output/f'position-{i:03d}/COLOR/same-frame.png')),cv2.ROTATE_90_CLOCKWISE) for i in (0,800)]
    return appearance_check(*images,cfg['scan_roi'],limit=3.)

def run(output,data_root=Path('/userdata/afc03-scanner/jobs')):
    require(output.parent.resolve()==data_root.resolve(),'Full scan must use data partition')
    output.mkdir(exist_ok=False)
    user=pwd.getpwnam('afcscanner');os.chown(output,user.pw_uid,user.pw_gid)
    shutil.copytree(ROOT/'new-strategy-bundle',output/'bundle')
    state=dict(status='running',mode='full',object_name='brown-dog',final_extraction='fpga-brightcore-scheme2-rk-geometry-dma-v1',phase='preflight',pid=os.getpid(),
        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),passed=False,
        points_are_static_profile=False,absolute_accuracy_validated=False,
        planned_intervals=800,commanded_step_deg=.45,last_index=-1,lasers={},
        completed_positions=0,capture_retries=0,retained_points={'A':0,'B':0},
        angle_source='commanded_pulses_no_encoder',automatic_resume=False)
    write(output/'status.json',state);start=time.perf_counter();empty=0;sizes=[]
    def check():
        pipeline.check()
        require(not (output/'STOP').exists(),'Operator stop requested')
        require(shutil.disk_usage(output).free>1024**3,'Data partition below 1 GiB reserve')
    pipeline=ScanPipeline(capacity=2)
    def consume(done):
        nonlocal empty
        if done is None:return
        folder=done['folder'];index=int(folder.name.split('-')[-1]);report=done['report']
        for label in ('A','B'):
            header=json.loads((folder/label/'frame.json').read_text())
            require(header['angle']['emitted_after']==origin+4*index,'Capture angle mismatch')
            state['retained_points'][label]+=report['lasers'][label]['retained_points']
        if index==0:
            require(report['scan_ready'],'Initial dual-laser point count below minimum')
            require(60<report['color']['median_max']<245 and report['color']['saturated_fraction']<.15,
                    'Initial colour exposure needs adjustment; no motor movement issued')
        total=sum(x['retained_points'] for x in report['lasers'].values())
        empty=empty+1 if total<10 else 0
        require(empty<10,'Both profiles lost for 10 consecutive positions')
        sizes.append(done['stored_bytes'])
        for f in folder.glob('*/report.json'):
            r=json.loads(f.read_text());state['capture_retries']+=max(0,r.get('capture_attempts',1)-1)
        state.update(last_index=index,completed_positions=index+1,lasers=report['lasers'],color=report['color'],
            commanded_degrees=index*.45,elapsed_seconds=time.perf_counter()-start,
            stored_bytes=sum(sizes),mean_position_seconds=(time.perf_counter()-start)/(index+1))
        state['estimated_remaining_seconds']=(800-index)*state['mean_position_seconds']
        state['pipeline']=dict(capacity=pipeline.capacity,high_water=pipeline.high_water,pending=len(pipeline.pending),last_storage_seconds=done['storage_seconds'])
        write(output/'status.json',state)
        print(json.dumps({k:state[k] for k in ('last_index','commanded_degrees','elapsed_seconds','capture_retries')}),flush=True)
        require(shutil.disk_usage(output).free>max(sizes[-10:])*(800-index)*1.25+1024**3,
                'Remaining capacity below projected scan size plus reserve')
    lock=None
    try:
        lock=open('/run/lock/afc03-fpga-scan.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        require(shutil.disk_usage(output).free>3*1024**3,'Insufficient startup storage')
        b=MotorBridge(PORT)
        try:
            initial=motor_state(b);b.send('LASER OFF');b.send('LED 0')
            b.send('PULSE_ARM '+str(initial['session']));b.send('PULSE_DISARM');time.sleep(.6)
            held=motor_state(b);require(held['session']==initial['session'] and held['emitted']==initial['emitted'],'Motor state changed during hold setup');initial=held
        finally:b.close()
        origin=initial['emitted'];session=initial['session'];state['initial_motor']=initial
        for index in range(801):
            check()
            while len(pipeline.pending)>=pipeline.capacity:consume(pipeline.retire(wait=True))
            while pipeline.pending and pipeline.pending[0]['stored'].done():consume(pipeline.retire())
            if index:
                state['phase']='moving';state['target_index']=index;write(output/'status.json',state)
                b=MotorBridge(PORT)
                try:
                    before=motor_state(b)
                    require(before['session']==session and before['emitted']==origin+4*(index-1),'Motor session/position changed')
                    move_once(b,before,4,40,output/f'move-{index:03d}.json',check)
                finally:b.close()
                time.sleep(.6)
            state['phase']='acquiring';write(output/'status.json',state)
            folder=output/f'position-{index:03d}'
            report=acquire(folder,output/'bundle',False,zero_pulses=origin,
                expected_motor=dict(session=session,emitted=origin+index*4),
                external_check=check,scan_lock_owned=True,color_led=8,pipeline=pipeline)
            if index==0:consume(pipeline.retire(wait=True))
            while pipeline.pending and pipeline.pending[0]['stored'].done():consume(pipeline.retire())
            if index==13:
                while pipeline.pending:consume(pipeline.retire(wait=True))
                state.update(phase='pilot_review',pilot_degrees=5.85);write(output/'status.json',state)
                deadline=time.monotonic()+900
                while not (output/'CONTINUE_AFTER_PILOT').exists():
                    check();require(time.monotonic()<deadline,'Pilot review timed out');time.sleep(1)
                state['pilot_review_released']=True
        while pipeline.pending:consume(pipeline.retire(wait=True))
        state['phase']='closure_check';write(output/'status.json',state)
        state['closure']=closure(output);write(output/'status.json',state)
        require(state['closure']['passed'],'Full-turn image closure failed; retain all data for review')
        state['phase']='merging';write(output/'status.json',state)
        # 360 degree frame is validation only, not duplicated in the model.
        state['model_points']=merge(output,range(800))
        state.update(status='complete',phase='complete',passed=True,
            scan_ready=False,scan_ready_scope='Full acquisition and closure passed; dimensional accuracy remains unvalidated')
    except BaseException as e:
        state.update(status='paused',phase='stopped',error=type(e).__name__+': '+str(e),passed=False)
        raise
    finally:
        try:
            b=MotorBridge(PORT)
            try:
                b.send('STOP');b.send('LASER OFF');b.send('LED 0');state['final_motor']=motor_state(b)
            finally:b.close()
        except Exception as e:state['cleanup_error']=str(e);state.update(status='paused',passed=False)
        try:pipeline.close()
        except Exception as e:
            state['pipeline_error']=str(e);state.update(status='paused',passed=False)
        state['elapsed_seconds']=time.perf_counter()-start;write(output/'status.json',state)
        if lock is not None:lock.close()
        # Keep a clearly labelled review model even if final closure rejects it.
        if state.get('last_index')==800 and not state.get('passed'):
            try:
                from review_scan import review
                review(output)
            except Exception as e:
                state['review_error']=str(e);write(output/'status.json',state)
    return state

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(KeyboardInterrupt()))
    cv2.setNumThreads(2);run(a.output)
