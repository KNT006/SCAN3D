"""Finite read-only camera/recorded-data measurements. Never imports motor control."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time
import urllib.request
import cv2
import numpy as np
from timing import statistics
from live_geometry import stripe,write_json


def fetch(url):
    with urllib.request.urlopen(url,timeout=8) as r:return r.read(),dict(r.headers)


def compare(a,b):
    a=cv2.resize(cv2.cvtColor(a,cv2.COLOR_BGR2GRAY),(960,540)).astype(np.float32)
    b=cv2.resize(cv2.cvtColor(b,cv2.COLOR_BGR2GRAY),(960,540)).astype(np.float32)
    shift,response=cv2.phaseCorrelate(a,b)
    return dict(shift_raw_px=[float(v*2) for v in shift],response=float(response),
                suspect_displacement=bool(response>.4 and np.linalg.norm(shift)*2>3),
                unobservable=bool(response<=.4))


def main(args):
    dest=args.output;dest.mkdir(parents=True,exist_ok=False)
    state=json.loads(fetch(args.app+'/api/status')[0])
    if any(state.get(k) for k in ['active_scans','active_jobs','active_calibrations']):raise RuntimeError('Board busy')
    started=time.monotonic();cpu=time.process_time();first=None;previous=None;last_identity=None
    status_start=json.loads(fetch(args.camera+'/status')[0]);samples=[];errors=[]
    for i in range(args.frames):
        if i%10==0:
            state=json.loads(fetch(args.app+'/api/status')[0])
            if any(state.get(k) for k in ['active_scans','active_jobs','active_calibrations']):
                errors.append(dict(index=i,error='Concurrent board task started; diagnostic stopped'));break
        try:
            t=time.monotonic();payload,headers=fetch(args.camera+'/capture.ppm');received=time.monotonic()
            im=cv2.imdecode(np.frombuffer(payload,np.uint8),cv2.IMREAD_COLOR);decoded=time.monotonic()
            if im is None or im.shape!=(1080,1920,3):raise RuntimeError('Invalid frame format')
            identity=(headers.get('X-Raw-Stream'),int(headers['X-Raw-Sequence']))
            if last_identity and (identity[0]!=last_identity[0] or identity[1]<=last_identity[1]):raise RuntimeError('Raw sequence reset/repeat')
            last_identity=identity
            row=dict(index=i,sequence=identity[1],stream=identity[0],pts_ns=headers.get('X-Raw-PTS-Ns'),
                     http_ms=(received-t)*1000,decode_ms=(decoded-received)*1000,
                     server_wait_ms=float(headers['X-Capture-Wait-Ms']),copy_ms=float(headers['X-Raw-Copy-Ms']),
                     sha256=hashlib.sha256(payload).hexdigest())
            if first is None:
                first=im.copy();cv2.imwrite(str(dest/'first.png'),im)
            row['against_first']=compare(first,im)
            if previous is not None:row['against_previous']=compare(previous,im)
            if any(row[k]['suspect_displacement'] for k in ('against_first','against_previous') if k in row):
                cv2.imwrite(str(dest/f'suspect-{i:03d}.png'),im)
            if i<12:
                # Test the same imwrite API as scanning; fsync is reported separately.
                p=dest/'write-probe.png';t=time.monotonic()
                if not cv2.imwrite(str(p),im):raise OSError('PNG write failed')
                row['png_write_ms']=(time.monotonic()-t)*1000;row['png_bytes']=p.stat().st_size
                t=time.monotonic()
                with p.open('rb') as f:os.fsync(f.fileno())
                row['png_fsync_ms']=(time.monotonic()-t)*1000
                if not np.array_equal(cv2.imread(str(p)),im):raise RuntimeError('PNG readback differs')
            samples.append(row);previous=im
        except Exception as exc:errors.append(dict(index=i,error=str(exc)))
        if i%20==0:print(f'capture {i+1}/{args.frames}',flush=True)
        time.sleep(args.interval)
    status_end=json.loads(fetch(args.camera+'/status')[0]);duration=time.monotonic()-started
    report=dict(kind='stationary_acquisition_diagnostic',hardware_actions='none; no motor, gain, LED or laser commands',
                frames_requested=args.frames,frames_received=len(samples),duration_seconds=duration,
                cpu_seconds=time.process_time()-cpu,peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
                environment=dict(opencv=cv2.__version__,opencv_threads=cv2.getNumThreads(),
                                 local_browser_and_preview_active=True),status_start=status_start,status_end=status_end,
                observed_raw_callback_fps=(status_end['raw_frames']-status_start['raw_frames'])/duration,
                samples=samples,errors=errors,
                statistics={k:statistics([v[k] for v in samples if k in v]) for k in
                            ('http_ms','decode_ms','server_wait_ms','copy_ms','png_write_ms','png_fsync_ms')},
                suspects=sum(v['against_first']['suspect_displacement'] or v.get('against_previous',{}).get('suspect_displacement',False) for v in samples),
                low_confidence=sum(v['against_first']['unobservable'] for v in samples),
                limitations=['Static scene assumed, motion/exposure can also cause differences',
                             'Application sequence is not an FPGA frame ID; does not prove DMA frame boundaries',
                             'Kernel may pad short frames; valid shape is insufficient',
                             'PNG write uses page cache; fsync separately measured; no end-to-end scan time claim'])
    write_json(dest/'capture_report.json',report)
    print(json.dumps({k:report[k] for k in ['frames_received','suspects','low_confidence','duration_seconds','statistics']}),flush=True)
    if args.recorded:
        import stripe_baseline
        src=args.recorded;cfg=json.loads((src/'scan_config.json').read_text());bg=cv2.rotate(cv2.imread(str(src/'background.png')),cv2.ROTATE_90_CLOCKWISE)
        tests=[]
        for f in sorted(src.glob('position*_laser_on*.png')):
            t=time.monotonic();raw=cv2.imread(str(f));read_ms=(time.monotonic()-t)*1000
            if raw is None:raise RuntimeError('Missing recorded frame')
            t=time.monotonic();im=cv2.rotate(raw,cv2.ROTATE_90_CLOCKWISE);rotation_ms=(time.monotonic()-t)*1000
            # Alternate evaluation order to reduce cache/order bias.
            funcs=[('baseline',stripe_baseline.stripe),('roi',stripe)]
            if len(tests)%2:funcs.reverse()
            result={};timings={}
            for name,fn in funcs:
                t=time.monotonic();result[name]=fn(im,bg,cfg['roi']);timings[name+'_ms']=(time.monotonic()-t)*1000
            a,b=result['baseline'],result['roi']
            same=np.array_equal(a[0],b[0]) and np.array_equal(a[1],b[1]) and a[2]==b[2]
            tests.append(dict(file=f.name,png_read_ms=read_ms,rotation_ms=rotation_ms,equal=bool(same),points=len(b[0]),**timings))
            if len(tests)%60==0:print('replay',len(tests),flush=True)
        retries=[]
        for f in src.glob('attempts/**/frame_rejection.json'):
            retries.append(dict(path=f.relative_to(src).as_posix(),**json.loads(f.read_text())))
        result=dict(source=str(src),roi=cfg['roi'],frames=len(tests),all_exact=all(t['equal'] for t in tests),
                    statistics={k:statistics([t[k] for t in tests]) for k in ('png_read_ms','rotation_ms','baseline_ms','roi_ms')},
                    frame_rejections=retries,measurements=tests,limitation='Image processing benchmark only; no mechanical timing measured')
        write_json(dest/'replay_report.json',result)
        print(json.dumps({k:result[k] for k in ['frames','all_exact','statistics']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--recorded',type=Path)
    p.add_argument('--frames',type=int,default=120);p.add_argument('--interval',type=float,default=.3)
    p.add_argument('--camera',default='http://127.0.0.1:8080');p.add_argument('--app',default='http://127.0.0.1:8081')
    args=p.parse_args()
    if not 1<=args.frames<=300 or not .1<=args.interval<=2:p.error('Bounded diagnostic required')
    main(args)
