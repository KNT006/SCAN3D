"""Static gain transaction and fresh RGB verification. No motion or light commands."""
import argparse, ctypes, fcntl, json, mmap, os, subprocess, sys, time
from contextlib import ExitStack
from pathlib import Path
from urllib.request import urlopen
import cv2
import numpy as np

p=argparse.ArgumentParser();p.add_argument('--count',type=int,default=100);p.add_argument('--out',required=True)
a=p.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
report=dict(passed=False,motor_operations=False,laser_operations=False,lighting_operations=False,records=[])
def status(port=8080,path='/status'):
    with urlopen(f'http://127.0.0.1:{port}{path}',timeout=5) as r:return json.load(r)
def capture():
    with urlopen('http://127.0.0.1:8080/capture.ppm',timeout=8) as r:
        headers=dict(r.headers);im=cv2.imdecode(np.frombuffer(r.read(),np.uint8),cv2.IMREAD_COLOR)
    assert im is not None and im.shape==(1080,1920,3), 'Invalid RGB frame'
    return im,headers
with ExitStack() as stack:
    for name in ('afc03-fpga-scan.lock','afc03-ddr-diag.lock','afc03-rgb-roi-diag.lock'):
        lock=stack.enter_context(open('/run/lock/'+name,'a'));fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    st=status(8081,'/api/status');assert not any(st.get(k) for k in ('active_scans','active_jobs','active_calibrations'))
    nodes=[Path('/dev')/x.parent.name for x in Path('/sys/class/video4linux').glob('video*/name') if 'milianke' in x.read_text().lower()]
    assert len(nodes)==1;node=str(nodes[0])
    base=int(Path('/sys/bus/pci/devices/0000:21:00.0/resource').read_text().split()[0],16)
    fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC);stack.callback(os.close,fd)
    mem=stack.enter_context(mmap.mmap(fd,4096,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ|mmap.PROT_WRITE,offset=base))
    def read(off):return ctypes.c_uint32.from_buffer(mem,off).value
    def set_gain(gain):
        prev=read(0x84)>>24;t=time.monotonic()
        subprocess.run(['v4l2-ctl','-d',node,'--set-ctrl=gain='+str(gain)],check=True,capture_output=True)
        while time.monotonic()-t<1:
            reg=read(0x84);delta=((reg>>24)-prev)&255
            if delta:
                assert delta==1 and reg&(1<<13) and not reg&((1<<14)|(1<<3)),f'Bad completed transaction: {reg:#x}, delta {delta}'
                assert read(0x98)&255==gain
                return dict(status=hex(reg),counter_delta=delta,ack_ms=(time.monotonic()-t)*1000)
            time.sleep(.001)
        raise RuntimeError('Gain transaction did not complete')
    original=read(0x98)&255;report['original_gain']=original;report['camera_before']=status();report['frame_before']=read(0x88)
    try:
        last_seq=-1
        for i in range(a.count):
            gain=0 if i%2==0 else 50
            txn=set_gain(gain)
            # Deliberately settled static validation, not a scan latency benchmark.
            time.sleep(.20+(i%7)*.003)
            im,headers=capture();seq=int(headers['X-Raw-Sequence'])
            assert seq>last_seq;last_seq=seq
            gray=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY)
            rec=dict(index=i,gain=gain,sequence=seq,stream=headers['X-Raw-Stream'],median=float(np.median(gray)),roi_median=float(np.median(gray[350:700,600:1000])),mean=float(gray.mean()),black_fraction=float((gray<=3).mean()),**txn)
            report['records'].append(rec)
            if i<2 or i>=a.count-2:cv2.imwrite(str(out/f'gain-{gain}-{i:03d}.jpg'),im)
            if (i+1)%10==0:print(json.dumps(dict(completed=i+1,last=rec)),flush=True)
        med={g:np.array([r['median'] for r in report['records'] if r['gain']==g]) for g in (0,50)}
        report['brightness']={str(g):dict(min=float(v.min()),max=float(v.max()),median=float(np.median(v))) for g,v in med.items()}
        assert med[50].min()>med[0].max()+5,'High and low gain brightness are not separated'
        assert all(v.max()-v.min()<=max(6,float(np.median(v))*.15) for v in med.values()),'Brightness inconsistent at fixed gain'
        report['gain_test_passed']=True
    except Exception as e:
        report['error']=repr(e)
    finally:
        try:
            if (read(0x98)&255)!=original:report['restore']=set_gain(original)
            report['restored_gain']=read(0x98)&255
        except Exception as e:report['restore_error']=repr(e)
        time.sleep(.3);report['camera_after']=status();report['frame_after']=read(0x88)
        before=report['camera_before'];after=report['camera_after']
        report['camera_healthy']=after['raw_age']<1 and after['frames']>before['frames'] and after['stream_id']==before['stream_id'] and all(after.get(k,0)==before.get(k,0) for k in ('raw_bad_sizes','raw_timeouts','raw_pts_nonmonotonic'))
        report['passed']=bool(report.get('gain_test_passed') and report['camera_healthy'] and report.get('restored_gain')==original and not report.get('restore_error'))
        (out/'validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps({k:v for k,v in report.items() if k!='records'}),flush=True)
sys.exit(0 if report['passed'] else 1)
