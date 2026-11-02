"""Board-side full ROI -> validated centers -> calibrated points. No motor movement.

Explicit CLI acquisition controls A/B electrically; motor remains disabled.
Raw matching frames are kept for independent software replay and timing.
"""
import argparse,dataclasses,fcntl,hashlib,json,secrets,signal,sys,time,zlib,subprocess,re,os
from pathlib import Path
from contextlib import ExitStack
import numpy as np
from role_capture import capture,BackgroundMMIO
from role_client import RoleClient,BackgroundIdentity
from job_client import JobClient
from rk_rgb_roi_diag import Probe,CameraAPI,scanner_idle,parse_ppm
from full_roi import receive_full_roi
from pointcloud_adapter import PointCloudAdapter
from dual_identity import geometry_candidates
from row_results import require
from capture_retry import capture_with_retry

PORT='/run/afc03-controller/control.sock'
ROOT=Path(__file__).resolve().parent

def write(path,obj):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(obj,indent=2,allow_nan=False));tmp.replace(path)

def motor_state(bridge):
    fields=dict(x.split('=',1) for x in bridge.send('PULSE_STATE').split()[2:] if '=' in x)
    for key in ('session','emitted','moving','pending','count_known','armed'):fields[key]=int(fields[key])
    require(fields['moving']==fields['pending']==fields['armed']==0 and fields['count_known']==1,
            'Motor not stationary/disarmed or pulse position unknown')
    require(fields['fault'] in ('none','disabled','stopped'), 'Motor fault')
    return fields

def unchanged(before,after):
    require((before['session'],before['emitted'])==(after['session'],after['emitted']),
            'Controller reset or pulse count changed; discard frame')

def software_check(off_file,on_file,frame):
    """Independent integer-reference evaluation, exact rational/window comparison."""
    from integer_peaks import prepare
    import row_model
    from fractions import Fraction
    images=[]
    for file in (off_file,on_file):
        w,h,raw=parse_ppm(file.read_bytes());images.append(np.frombuffer(raw,np.uint8).reshape(h,w,3))
    off,on=images;x0,y0,x1,y1=frame.header['geometry']['roi_xyxy'];actual={}
    for center in frame.centers:actual.setdefault(center.row,[]).append(center)
    for row in range(y0,y1):
        sig,mx,smooth,base,peaks,_=prepare(on[::-1,row,:],off[::-1,row,:],x0,x1-1)
        candidates=row_model.evaluate(sig,mx,smooth,base,peaks,x0,x1-1);chosen=[]
        for r in sorted((r for r in candidates if r['reason']==0),key=lambda r:-r['peak32']):
            if all(abs(r['num']*q['den']-q['num']*r['den'])>=8*r['den']*q['den'] and
                   (r['hi']<q['lo'] or r['lo']>q['hi']) for q in chosen):chosen.append(r)
            if len(chosen)==2:break
        chosen.sort(key=lambda r:Fraction(r['num'],r['den']))
        expected=[tuple(r[k] for k in ('num','den','peak32','lo','hi')) for r in chosen]
        got=[(r.num,r.den,r.peak32,r.lo,r.hi) for r in actual.get(row,[])]
        require(got==expected,'Software comparison failed at processing row '+str(row))
    return dict(passed=True,rows=y1-y0,centers=len(frame.centers),exact=True)

def acquire(output,bundle,compare=True,zero_pulses=None,expected_motor=None,external_check=None,scan_lock_owned=False,color_led=None):
    output.mkdir(parents=True,exist_ok=False)
    report=dict(status='running',motor_operations=False,points_are_static_profile=True,
                absolute_accuracy_validated=False,transport='mailbox',timings={},lasers={},
                pid=os.getpid(),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    started=time.perf_counter();write(output/'status.json',report)
    from rk_motor import MotorBridge
    cfg=json.loads((bundle/'config.json').read_text());roi=cfg['scan_roi']
    geom=dict(raw_size_wh=[1920,1080],processing_size_wh=[1080,1920],rotation_cw=90,
              roi_xyxy=roi,global_x_origin=0,row_input_width=1080)
    geometry_revision=zlib.crc32(json.dumps(geom,sort_keys=True).encode()) or 1
    adapter=PointCloudAdapter(bundle,geometry_candidates)
    calibration=dict(version='dual-20260930',**adapter.hashes)
    calibration_revision=zlib.crc32(json.dumps(calibration,sort_keys=True).encode()) or 1
    epoch=secrets.randbelow(2**31-1)+1
    try:
        with ExitStack() as stack:
            if not scan_lock_owned:
                f=stack.enter_context(open('/run/lock/afc03-fpga-scan.lock','a'));fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            for name in ('afc03-ddr-diag.lock','afc03-rgb-roi-diag.lock'):
                f=stack.enter_context(open('/run/lock/'+name,'a'));fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            scanner_idle('http://127.0.0.1:8081')
            bridge=MotorBridge(PORT);stack.callback(bridge.close)
            require(bridge.send('PING').split()[:2]==['OK','rk_control_v1'],'Unexpected controller')
            before=motor_state(bridge)
            if expected_motor is not None:unchanged(expected_motor,before)
            def lights_off():
                try:bridge.send('LASER OFF')
                finally:bridge.send('LED 0')
            stack.callback(lights_off);lights_off()
            nodes=[Path('/dev')/p.parent.name for p in Path('/sys/class/video4linux').glob('video*/name')
                   if 'milianke' in p.read_text().lower()]
            require(len(nodes)==1,'Cannot uniquely identify FPGA camera')
            device=str(nodes[0]);gain=int(cfg['gain_geometry'])
            require(0<=gain<=240,'Invalid geometry gain')
            previous=subprocess.check_output(['v4l2-ctl','-d',device,'--get-ctrl=gain'],text=True).strip()
            subprocess.run(['v4l2-ctl','-d',device,'--set-ctrl=gain='+str(gain)],check=True)
            current=subprocess.check_output(['v4l2-ctl','-d',device,'--get-ctrl=gain'],text=True).strip()
            require(current=='gain: '+str(gain),'Camera gain readback mismatch')
            report['camera_profile']=dict(device=device,before=previous,applied=current)
            probe=Probe();stack.callback(probe.close);mmio=BackgroundMMIO(probe);api=CameraAPI()
            # A/B share one live mailbox. Rebase request ID when changing clients.
            def client(role):return RoleClient(mmio.read,mmio.write,role=role,poll_seconds=0)
            job=JobClient(mmio.read,mmio.write)
            def snap(role):return client(role).snapshot()
            def check():
                if external_check is not None:external_check()
                unchanged(before,motor_state(bridge))
                require(not (output/'STOP').exists(),'Stop requested')
            def shot(role,path):
                check();t=time.perf_counter()
                r=capture_with_retry(path,
                    lambda target:capture(probe,client(role),api,target,epoch,geometry_revision,calibration_revision,5),check)
                require(r['passed'], 'Capture rejected: '+str(r.get('error',r)))
                r['role']=role;write(path/'report.json',r);check()
                return r,time.perf_counter()-t
            time.sleep(.25);bg,bg_seconds=shot(0,output/'OFF')
            report['timings']['background_capture_and_save_s']=bg_seconds
            stream=bg['camera_arm']['stream_id'];bg_id=BackgroundIdentity(**bg['background'])
            for role,label in ((1,'A'),(2,'B')):
                check();bridge.send('LASER '+label)
                try:
                    time.sleep(.25)
                    state=bridge.send('LASERSTATE')
                    require(('A=1 B=0' if role==1 else 'A=0 B=1') in state,'Wrong laser output state')
                    on,seconds=shot(role,output/label)
                finally:bridge.send('LASER OFF')
                require(on['camera_arm']['stream_id']==stream,'Camera restarted across captures')
                on_id=BackgroundIdentity(**on['background']);after=motor_state(bridge);unchanged(before,after)
                angle=dict(source='commanded_pulses_no_encoder',moving_before=False,moving_after=False,
                    emitted_before=before['emitted'],emitted_after=after['emitted'],zero_pulses=before['emitted'] if zero_pulses is None else zero_pulses,
                    pulses_per_revolution=cfg['pulses_per_revolution'],command_complete=True)
                context=dict(stream_epoch=stream,background_generation=bg_id.generation,geometry=geom,
                    laser_id=label,laser_control='electrical_single_laser',calibration=calibration,
                    algorithm='fpga_full_row_right_tie_v1')
                t=time.perf_counter()
                frame,stats=receive_full_roi(job,snap,context,angle,bg_id,on_id,epoch,geometry_revision,
                    calibration_revision,100+role*100,check)
                extract_seconds=time.perf_counter()-t
                # Verify the camera process epoch again before publishing any geometry.
                require(api.request('/diagnostic/roi/status')['stream_id']==stream,'Camera epoch changed')
                t=time.perf_counter();cloud=adapter.reconstruct(frame)
                unique={r.row for r in frame.rows if r.count==1}
                mask=np.array([frame.centers[i].row in unique for i in cloud['kept_record_indices']],bool)
                arrays={k:cloud[k][mask] for k in ('uv','camera_xyz_mm','camera_aligned_mm','axis_frame_mm')}
                geometry_seconds=time.perf_counter()-t
                comparison=None;t=time.perf_counter()
                if compare:comparison=software_check(output/'OFF/same-frame.ppm',output/label/'same-frame.ppm',frame)
                compare_seconds=time.perf_counter()-t
                check()
                np.savez_compressed(output/label/'points.npz',**arrays)
                (output/label/'records.bin').write_bytes(frame.payload)
                write(output/label/'frame.json',frame.header)
                report['lasers'][label]=dict(stats,retained_points=len(arrays['uv']),
                    turntable_filter=cloud.get('turntable_filter'),
                    multiple_peak_rows_rejected=sum(r.count>1 for r in frame.rows),comparison=comparison,
                    capture_and_raw_save_s=seconds,extract_and_receive_s=extract_seconds,
                    rk_geometry_s=geometry_seconds,software_reference_s=compare_seconds)
                write(output/'status.json',report)
            if color_led is not None:
                require(type(color_led)is int and 1<=color_led<=8,'Invalid colour light level')
                check();bridge.send('LASER OFF')
                require('A=0 B=0' in bridge.send('LASERSTATE'),'Lasers not commanded off for colour')
                bridge.send('LED '+str(color_led))
                try:
                    subprocess.run(['v4l2-ctl','-d',device,'--set-ctrl=gain=50'],check=True)
                    require(subprocess.check_output(['v4l2-ctl','-d',device,'--get-ctrl=gain'],text=True).strip()=='gain: 50','Colour gain mismatch')
                    time.sleep(.4);colour,seconds=shot(0,output/'COLOR')
                finally:
                    bridge.send('LED 0')
                    subprocess.run(['v4l2-ctl','-d',device,'--set-ctrl=gain='+str(gain)],check=True)
                require(colour['camera_arm']['stream_id']==stream,'Camera changed during colour capture')
                w,h,raw=parse_ppm((output/'COLOR/same-frame.ppm').read_bytes())
                rgb=np.rot90(np.frombuffer(raw,np.uint8).reshape(h,w,3),-1)
                from scan_storage import sample_rgb
                samples=[]
                for label in ('A','B'):
                    file=output/label/'points.npz'
                    with np.load(file,allow_pickle=False) as f:arrays={k:f[k] for k in f.files}
                    arrays['rgb']=sample_rgb(rgb,arrays['uv']);samples.append(arrays['rgb'])
                    np.savez_compressed(file,**arrays)
                all_rgb=np.concatenate(samples)
                report['color']=dict(led=color_led,gain=50,capture_and_save_s=seconds,
                    samples=len(all_rgb),median_max=float(np.median(all_rgb.max(1))) if len(all_rgb) else 0,
                    saturated_fraction=float(np.mean(all_rgb.max(1)>=250)) if len(all_rgb) else 0,
                    stream_id=stream,frame_id=colour['background']['source_frame'],same_commanded_position=True)
            report.update(status='complete',passed=True,
                scan_ready=all(r['retained_points']>=30 for r in report['lasers'].values()),
                scan_ready_scope='Static point-count gate only; repeatability, motor and cold boot still pending')
    except BaseException as e:
        report.update(status='failed',passed=False,error=type(e).__name__+': '+str(e));raise
    finally:
        report['elapsed_seconds']=time.perf_counter()-started;write(output/'status.json',report)
    return report

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--bundle',type=Path,default=ROOT/'bundle');p.add_argument('--skip-reference',action='store_true')
    p.add_argument('--color-led',type=int,choices=range(1,9))
    a=p.parse_args();signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(KeyboardInterrupt()))
    print(json.dumps(acquire(a.output,a.bundle,not a.skip_reference,color_led=a.color_led),indent=2))
if __name__=='__main__':main()
