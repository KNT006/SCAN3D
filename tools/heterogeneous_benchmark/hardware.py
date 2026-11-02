"""Explicitly authorized stationary OFF/A/B capture and ABI6 fixed-frame benchmark.

No motor movement, reference reset, firmware programming or production edits.
Run on the RK, using its installed capture/transport implementation.
"""
import argparse, contextlib, dataclasses, hashlib, json, secrets, subprocess, sys, time, zlib
from pathlib import Path


def records(payload):
    from row_results import decode_record, Center, CandidateExtra, RowDone
    items=[decode_record(payload[i:i+16]) for i in range(0,len(payload),16)]
    centers=[x for x in items if isinstance(x,Center)]
    extra={(x.row,x.index):x for x in items if isinstance(x,CandidateExtra)}
    rows=[x for x in items if isinstance(x,RowDone)]
    if any(x.error for x in rows): raise ValueError('Hardware row error')
    if len(extra)!=len(centers): raise ValueError('Missing candidate metadata')
    return [[c.row,c.num,c.den,c.peak32,c.lo,c.hi,extra[c.row,c.index].peak_x,extra[c.row,c.index].strength] for c in centers]


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--capture-confirmed',action='store_true');p.add_argument('--repeats',type=int,default=5)
    a=p.parse_args()
    if not a.capture_confirmed:p.error('Explicit stationary capture authorization required')
    if a.output.exists():p.error('Choose a new output directory')
    if not 1<=a.repeats<=10:p.error('repeats 1..10')
    sys.path[:0]=['/opt/afc03-scanner/fpga','/opt/afc03-motor']
    import fcntl,cv2
    from rk_rgb_roi_diag import Probe,CameraAPI
    from role_capture import BackgroundMMIO,capture
    from role_client import RoleClient,BackgroundIdentity
    from job_client import JobClient
    from rk_motor import MotorBridge
    from run import check_idle,environment
    base=Path('/opt/afc03-scanner/fpga');cfg=json.loads((base/'new-strategy-bundle/config.json').read_text())
    roi=cfg['scan_roi'];left,top,right,bottom=roi
    report=dict(scope='fixed-input ABI6 candidate extraction including driver transport; no common RK postprocessing',
        clock_hz_verified=None,roi=roi,environment_start=environment(),captures={},trials={},cleanup={})
    a.output.mkdir(parents=True)
    def save(): (a.output/'hardware-results.json').write_text(json.dumps(report,indent=2))
    try:
      with contextlib.ExitStack() as stack:
        for name in ('afc03-fpga-scan.lock','afc03-ddr-diag.lock','afc03-rgb-roi-diag.lock'):
            f=stack.enter_context(open('/run/lock/'+name,'a'));fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        check_idle('http://127.0.0.1:8081/api/scan3d/status')
        b=MotorBridge('/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B7B026023-if00');stack.callback(b.close)
        def motor():
            d=dict(x.split('=',1) for x in b.send('PULSE_STATE').split()[2:] if '=' in x)
            if any(int(d[k]) for k in ('moving','pending','armed')):raise RuntimeError('Motor not stationary/disarmed')
            return d
        before=motor();report['motor_before']=before
        def check():
            check_idle('http://127.0.0.1:8081/api/scan3d/status')
            now=motor()
            if any(now[k]!=before[k] for k in ('session','emitted','count_known')):raise RuntimeError('Motor state changed')
        def lights_off():
            try:
                b.send('LASER OFF');b.send('LED 0');report['cleanup']['lasers']=b.send('LASERSTATE')
            except Exception as e:report['cleanup']['light_error']=str(e)
        stack.callback(lights_off);lights_off()
        nodes=[Path('/dev')/x.parent.name for x in Path('/sys/class/video4linux').glob('video*/name') if 'milianke' in x.read_text().lower()]
        if len(nodes)!=1:raise RuntimeError('Ambiguous camera')
        device=str(nodes[0]);old=subprocess.check_output(['v4l2-ctl','-d',device,'--get-ctrl=gain'],text=True).strip()
        def restore_gain():
            r=subprocess.run(['v4l2-ctl','-d',device,'--set-ctrl='+old.replace(': ','=')],capture_output=True,text=True)
            report['cleanup']['gain_restore_returncode']=r.returncode
        stack.callback(restore_gain)
        subprocess.run(['v4l2-ctl','-d',device,'--set-ctrl=gain='+str(cfg['gain_geometry'])],check=True)
        if subprocess.check_output(['v4l2-ctl','-d',device,'--get-ctrl=gain'],text=True).strip()!='gain: '+str(cfg['gain_geometry']):
            raise RuntimeError('Capture gain readback mismatch')
        report['gain_before']=old;report['gain_capture']=cfg['gain_geometry']
        probe=Probe();stack.callback(probe.close);mmio=BackgroundMMIO(probe);api=CameraAPI()
        job=JobClient(mmio.read,mmio.write);stack.callback(job.close)
        if not job.spatial_candidates:raise RuntimeError('Requires ABI6')
        report['registers']={hex(x):hex(mmio.read(x)) for x in (0x2400,0x2408,0x2434,0x2438)}
        def client(role):return RoleClient(mmio.read,mmio.write,role=role,poll_seconds=0)
        epoch=secrets.randbelow(2**30)+1;geom=zlib.crc32(json.dumps(roi).encode()) or 1;cal=1
        identities={}
        def benchmark_role(role,label):
            def stable():
                check()
                for cached_role in (0,role):
                    identity=identities[cached_role]
                    q=client(cached_role).snapshot()
                    if not q.active or q.background!=identity or q.flags&0x2d:raise RuntimeError('DDR frame changed')
            report['trials'][label]=[];baseline=None
            for iteration in range(a.repeats+1):
                stable();wall=time.perf_counter();cpu=time.process_time();batches=[];chunks=[]
                for y in range(top//4*4,bottom,60):
                    summary,payload=job.run(role=role,epoch=epoch,geometry=geom,calibration=cal,
                        token=1000+role*10000+iteration*100+(y-top)//60,width=1920,height=1080,
                        roi=[y,0,min(y+60,bottom),1080],left=left,right=right-1,
                        expected_bg=identities[0],expected_on=identities[role])
                    rows=records(payload)
                    if summary['rows']!=min(y+60,bottom)-y:raise RuntimeError('Incomplete batch')
                    chunks.append(payload);batches.append(dict(summary,receive_seconds=job.last_receive_seconds))
                payload=b''.join(chunks);exact=records(payload)
                trial=dict(warmup=iteration==0,wall_seconds=time.perf_counter()-wall,cpu_seconds=time.process_time()-cpu,
                    cycles=sum(x['cycles'] for x in batches),receive_seconds=sum(x['receive_seconds'] for x in batches),
                    payload_bytes=len(payload),payload_sha256=hashlib.sha256(payload).hexdigest(),candidates=len(exact),batches=batches)
                stable()
                if baseline is None:
                    baseline=exact;(a.output/label/'records.bin').write_bytes(payload)
                    sample=a.output/'samples'/label;sample.mkdir(parents=True)
                    for src,dst in (('OFF','OFF'),(label,label)):
                        im=cv2.imread(str(a.output/src/'same-frame.ppm'))
                        if not cv2.imwrite(str(sample/(dst+'.png')),im):raise RuntimeError('Image write failed')
                    (sample/'data.json').write_text(json.dumps(dict(request=dict(laser=label),roi=roi,
                        expected_records=exact,steps=[dict(uv=[[r[1]/r[2],r[0]] for r in exact])],
                        identities={str(k):dataclasses.asdict(v) for k,v in identities.items()})))
                elif exact!=baseline:raise RuntimeError('Repeated hardware output changed')
                report['trials'][label].append(trial);save();print(label,iteration,trial['wall_seconds'],flush=True)
        for role,label in ((0,'OFF'),(1,'A'),(2,'B')):
            check();b.send('LASER '+label)
            try:
                time.sleep(.25)
                state=b.send('LASERSTATE');expected=('A=0 B=0','A=1 B=0','A=0 B=1')[role]
                if expected not in state:raise RuntimeError('Laser state mismatch')
                r=capture(probe,client(role),api,a.output/label,epoch,geom,cal,5,verify_pixels=True,preflight_checked=True)
                report['captures'][label]=r;save()
                if not r['passed']:raise RuntimeError('Capture failed: '+str(r.get('error',r)))
                if role and r['camera_arm']['stream_id']!=report['captures']['OFF']['camera_arm']['stream_id']:
                    raise RuntimeError('Camera stream restarted across capture')
                identities[role]=BackgroundIdentity(**r['background'])
            finally:b.send('LASER OFF')
            if role:
                lights_off();benchmark_role(role,label)
        report['motor_after']=motor();report['passed']=True
    except BaseException as e:
        report['passed']=False;report['error']=repr(e);raise
    finally:
        if report['cleanup'].get('light_error') or report['cleanup'].get('gain_restore_returncode',0):report['passed']=False
        report['environment_end']=environment();save()


if __name__=='__main__':main()
