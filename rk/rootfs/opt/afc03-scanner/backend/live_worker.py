"""Finite, journaled board acquisition. One controller connection; no motion retries."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import cv2
import numpy as np
from timing import Timing, timed
from image_io import save_png
from live_geometry import write_json, stripe, repeat_error, stable_rows, closure_passes, reconstruct, colorize

PORT='/run/afc03-controller/control.sock'
CAMERA=os.environ.get('SCANNER_CAMERA_URL','http://192.168.1.89:8080')


def light_matches(reply, level):
    fields = dict(re.findall(r'(\w+)=([^ ]+)', reply))
    return reply.startswith('OK ') and fields.get('white') == str(level)


class Cancelled(Exception): pass


class Scan:
    def __init__(self, directory):
        self.timing=Timing(directory); self.last_raw=None
        self.p=directory; self.state=json.loads((directory/'live.json').read_text())
        self.cfg=json.loads((directory/'scan_config.json').read_text())
        self.io=threading.RLock(); self.state_lock=threading.RLock()
        self.cancel=threading.Event(); self.finished=threading.Event(); self.stopped=threading.Event()
        self.bridge=None; self.monitor=None; self.bg=None; self.angle=None

    def update(self, **fields):
        with self.state_lock:
            self.state.update(fields); write_json(self.p/'live.json',self.state)

    def check(self):
        if (self.p/'stop.request').exists(): self.cancel.set()
        if self.cancel.is_set(): raise Cancelled('Stop requested; this session cannot resume automatically')

    def sleep(self, seconds):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            self.check(); time.sleep(min(.05,max(0,deadline-time.monotonic())))

    def send(self, command):
        with self.io:
            self.check(); return self.bridge.send(command)

    def pos(self):
        reply=self.send('POS'); match=re.search(r'deg=(-?[\d.]+)',reply)
        if not match: raise RuntimeError('Invalid encoder reply: '+reply)
        return float(match[1])

    def monitor_stop(self):
        while not self.finished.wait(.05):
            if (self.p/'stop.request').exists(): self.cancel.set()
            if not self.cancel.is_set(): continue
            self.update(status='stopping',stage='stopping')
            try:
                with self.io:
                    reply=self.bridge.send('STOP'); samples=[]
                    for _ in range(15):
                        time.sleep(.2); r=self.bridge.send('POS'); m=re.search(r'deg=(-?[\d.]+)',r)
                        if not m: raise RuntimeError(r)
                        samples.append(float(m[1]))
                        if len(samples)>=3 and max(samples[-3:])-min(samples[-3:])<.06: break
                    settled=len(samples)>=3 and max(samples[-3:])-min(samples[-3:])<.06
                    self.update(stop_reply=reply,stop_verified=settled,stop_samples=samples,angle=samples[-1] if samples else self.angle)
            except Exception as exc:
                self.update(stop_verified=False,stop_error=str(exc))
            finally: self.stopped.set()
            return

    @timed('operator_wait')
    def wait_for(self, stage, choices):
        self.update(status='waiting',stage=stage,expected_actions=choices)
        # The API creates one exclusive request with the expected stage token.
        while True:
            self.sleep(.1); request=self.p/'action.request'
            if not request.exists(): continue
            value=json.loads(request.read_text()); request.unlink()
            if value.get('stage')!=stage or value.get('action') not in choices:
                raise RuntimeError('Out-of-order confirmation')
            self.update(status='running',expected_actions=[])
            return value['action']

    @timed('illumination_settings')
    def settings(self, gain, led):
        self.check()
        reply=self.send('LED '+str(led))
        if not light_matches(reply, led): raise RuntimeError(reply)
        result=subprocess.run(['v4l2-ctl','-d','/dev/video73',f'--set-ctrl=gain={gain}','--get-ctrl=gain'],capture_output=True,text=True,timeout=3,check=True)
        if f'gain: {gain}' not in result.stdout: raise RuntimeError('Gain not applied')
        self.update(gain=gain,led=led); self.sleep(1)

    @timed('capture_total')
    def frame(self):
        self.check()
        st=json.loads(urllib.request.urlopen(CAMERA+'/status',timeout=2).read())
        if st.get('age',999)>=2: raise RuntimeError('Camera stream is stale')
        with self.timing.span('raw_http'):
            with urllib.request.urlopen(CAMERA+'/capture.ppm',timeout=8) as response:
                payload=response.read();headers=response.headers
        self.check()
        if headers.get('X-Raw-Sequence'):
            identity=(headers['X-Raw-Stream'],int(headers['X-Raw-Sequence']))
            if self.last_raw:
                if identity[0]!=self.last_raw[0]:raise RuntimeError('Camera service restarted during acquisition')
                if identity[1]<=self.last_raw[1]:raise RuntimeError('Raw camera sequence did not advance')
            self.last_raw=identity
            st.update(preview_frames=st.get('frames'),frames=identity[1],raw_stream_id=identity[0],
                      raw_pts_ns=headers.get('X-Raw-PTS-Ns'),raw_monotonic_ns=headers.get('X-Raw-Monotonic-Ns'),
                      capture_wait_ms=float(headers['X-Capture-Wait-Ms']),raw_copy_ms=float(headers['X-Raw-Copy-Ms']),
                      counter_source='raw')
        else:st['counter_source']='legacy_preview'
        with self.timing.span('ppm_decode'):
            im=cv2.imdecode(np.frombuffer(payload,np.uint8),cv2.IMREAD_COLOR)
        if im is None or im.shape!=(1080,1920,3):raise RuntimeError('Unexpected camera format')
        return im,st

    @timed('pair_total')
    def pair(self, directory, label, suffix):
        for attempt in range(3):
            images=[]; counters=[]; files=[]
            for tail in [suffix,suffix+'_repeat']:
                im,st=self.frame(); target=directory/(label+'_'+tail+'.png')
                if target.exists(): raise RuntimeError('Refusing to overwrite a raw acquisition')
                with self.timing.span('png_write',file=target.name):
                    save_png(target,im)
                write_json(target.with_suffix('.frame.json'),st)
                files.append(target);images.append(cv2.rotate(im,cv2.ROTATE_90_CLOCKWISE));counters.append(st['frames']);self.sleep(.3)
            if counters[1]<=counters[0]: raise RuntimeError('Camera frame counter did not advance')
            gray=[cv2.resize(cv2.cvtColor(im,cv2.COLOR_BGR2GRAY),(540,960)).astype(np.float32) for im in images]
            shift,response=cv2.phaseCorrelate(*gray)
            bad=response>.4 and np.linalg.norm(shift)*2>3
            diagnostic=dict(phase_shift_fullframe_px=[x*2 for x in shift],phase_response=response,attempt=attempt,reason='whole-frame displacement; retry capture without motor command')
            reference=directory/('position000_'+suffix+'.png')
            if reference.exists() and label!='position000':
                ref=cv2.rotate(cv2.imread(str(reference)),cv2.ROTATE_90_CLOCKWISE)
                anchor=lambda im:cv2.cvtColor(im,cv2.COLOR_BGR2GRAY)[1400:1800,400:1000].astype(np.float32)
                for im in images:
                    offset,confidence=cv2.phaseCorrelate(anchor(ref),anchor(im))
                    if confidence>.5 and np.linalg.norm(offset)>3:
                        bad=True;diagnostic.update(anchor_shift_px=offset,anchor_response=confidence)
            if not bad:return images,counters
            archive=self.p/'attempts'/(label+'-'+suffix+'-frame-'+str(time.time_ns()));archive.mkdir(parents=True)
            for file in files:
                file.rename(archive/file.name)
                metadata=file.with_suffix('.frame.json')
                if metadata.exists():metadata.rename(archive/metadata.name)
            write_json(archive/'frame_rejection.json',diagnostic)
            self.update(frame_retries=self.state.get('frame_retries',0)+1)
            self.sleep(.5)
        raise RuntimeError('Repeated displaced camera frames; raw attempts saved and motor will stop')

    @timed('encoder_and_led_verify')
    def verify(self, angle, led):
        after=self.pos()
        if abs(after-angle)>.06: raise RuntimeError('Encoder moved during capture')
        reply=self.send('LEDSTATE')
        if not light_matches(reply, led): raise RuntimeError('LED changed during capture')
        return after

    @timed('motion_and_settle')
    def move_to(self, index, start, directory):
        self.check(); before=self.pos()
        if abs(before-self.angle)>.06: raise RuntimeError('Position changed before move')
        if self.send('ENSTATE')!='OK ENSTATE 1': raise RuntimeError('Motor is not enabled')
        pulses=round(index*3200/180)-round((index-1)*3200/180)
        motion=dict(index=index,before=before,pulses=pulses,status='reserved_before_dispatch_no_retry')
        journal=directory/f'position{index:03d}_motion.json'
        if journal.exists(): raise RuntimeError('Move already reserved; refusing retry')
        write_json(journal,motion); self.update(stage='moving',pending_index=index)
        with self.io:
            self.check(); ack=self.bridge.move(pulses,10)
        motion.update(status='dispatched',ack=ack); write_json(journal,motion)
        samples=[]
        for _ in range(40):
            self.sleep(.3); samples.append(self.pos())
            if len(samples)>=3 and max(samples[-3:])-min(samples[-3:])<.06 and abs(samples[-1]-before)>1: break
        angle=samples[-1]
        if len(samples)<3 or max(samples[-3:])-min(samples[-3:])>=.06: raise RuntimeError('Motor not settled')
        if abs(angle-before+pulses*360/3200)>.25: raise RuntimeError('Wrong motion increment')
        if abs(angle-start+round(index*3200/180)*360/3200)>.35: raise RuntimeError('Wrong cumulative angle')
        self.sleep(1)
        if abs(self.pos()-angle)>.06: raise RuntimeError('Position drift after settling')
        self.angle=angle; motion.update(status='settled',after=angle,samples=samples)
        write_json(journal,motion); return motion

    @timed('geometry_position')
    def geometry_capture(self, index, motion):
        label=f'position{index:03d}'; self.update(stage='capturing_geometry',index=index)
        pair,counters=self.pair(self.p,label,'laser_on')
        with self.timing.span('stripe_pair'):
            uv,widths,rejected=stripe(pair[0],self.bg,self.cfg['roi'])
            other,_,_=stripe(pair[1],self.bg,self.cfg['roi'])
        repeat=repeat_error(uv,other)
        stable=stable_rows(uv,other,3)
        quality=dict(points=len(uv),stable_points=int(stable.sum()),rejected=rejected,repeat=repeat,unstable_or_unmatched_rows=int((~stable).sum()))
        write_json(self.p/(label+'_quality.json'),quality)
        # Conservative stop on missing or unstable signal; save raw frames even on failure.
        if len(uv)<40 or repeat['matched']<30: raise RuntimeError('Too few laser rows; inspect lighting/occlusion/ROI')
        if repeat['median']>1.5 or stable.sum()<30: raise RuntimeError('Laser stripe unstable between stationary frames')
        after=self.verify(motion['after'],0)
        np.savez(self.p/(label+'_stripe.npz'),uv=uv,repeat_uv=other,widths=widths)
        write_json(self.p/(label+'_record.json'),dict(index=index,status='captured_and_verified',motion=motion,quality=quality,frame_counters=counters,verified_angle=after))
        self.update(phase='geometry',completed_positions=index+1,index=index,angle=after,quality=quality,progress=round((index+1)/181*45,1),pending_index=None)

    def run(self):
        sys.path.insert(0,str(Path(__file__).parent/'hardware'))
        from rk_motor import MotorBridge
        try:
            self.update(status='running',stage='connecting',expected_actions=[])
            self.bridge=MotorBridge(PORT)
            self.monitor=threading.Thread(target=self.monitor_stop,daemon=True); self.monitor.start()
            if self.send('ENSTATE')!='OK ENSTATE 1': raise RuntimeError('驱动器未使能，请先检查供电和模式')
            samples=[]
            for _ in range(3): samples.append(self.pos()); self.sleep(.3)
            if max(samples)-min(samples)>.06: raise RuntimeError('Motor is moving at startup')
            self.angle=samples[-1]
            resume_file=self.p/'resume.json'
            if resume_file.exists():
                resume=json.loads(resume_file.read_text());index=resume['index'];start=self.cfg['start_encoder_degrees']
                motion=json.loads((self.p/f'position{index:03d}_motion.json').read_text())
                if motion['status']!='settled' or abs(self.angle-motion['after'])>.06: raise RuntimeError('Resume encoder does not match the settled motion journal')
                if (self.p/f'position{index:03d}_record.json').exists(): raise RuntimeError('Position already verified; refusing re-acquisition')
                self.settings(10,0)
                self.bg=cv2.rotate(cv2.imread(str(self.p/'background.png')),cv2.ROTATE_90_CLOCKWISE)
                fresh=cv2.rotate(self.frame()[0],cv2.ROTATE_90_CLOCKWISE)
                x0,y0,x1,y1=self.cfg['roi']
                candidates=[]
                for suffix in ['laser_on','laser_on_repeat']:
                    original=cv2.rotate(cv2.imread(str(self.p/f'position{index:03d}_{suffix}.png')),cv2.ROTATE_90_CLOCKWISE)
                    gray=[cv2.cvtColor(im,cv2.COLOR_BGR2GRAY)[y0:y1,x0:x1].astype(np.float32) for im in [original,fresh]]
                    offset,confidence=cv2.phaseCorrelate(*gray)
                    if confidence>=.4 and np.linalg.norm(offset)<=2:candidates.append((offset,confidence,suffix))
                if not candidates:raise RuntimeError('Scene changed since stop; cannot continue the same scan')
                shift,response,reference_suffix=max(candidates,key=lambda x:x[1])
                archive=self.p/'attempts'/('position%03d-'%index+str(time.time_ns()));archive.mkdir(parents=True)
                for suffix in ['laser_on.png','laser_on_repeat.png','laser_on.frame.json','laser_on_repeat.frame.json','quality.json']:
                    f=self.p/(f'position{index:03d}_'+suffix)
                    if f.exists():f.rename(archive/f.name)
                write_json(archive/'resume_validation.json',dict(index=index,encoder=self.angle,phase_shift=shift,phase_response=response,reference_suffix=reference_suffix,motion_repeated=False))
                self.geometry_capture(index,motion);next_index=index+1
            else:
                start=self.angle;self.cfg['start_encoder_degrees']=start;write_json(self.p/'scan_config.json',self.cfg)
                self.settings(10,0); self.update(stage='capturing_background',angle=start)
                bg,counters=self.pair(self.p,'background','off'); self.bg=bg[0]
                shutil.copy2(self.p/'background_off.png',self.p/'background.png')
                self.verify(start,0)
                self.wait_for('await_laser_on',['laser_on'])
                if abs(self.pos()-start)>.06: raise RuntimeError('Object/turntable moved while waiting')
                self.geometry_capture(0,dict(before=start,after=start,pulses=0,samples=samples));next_index=1
            for i in range(next_index,181):
                motion=self.move_to(i,start,self.p); self.geometry_capture(i,motion)
                if i==3: self.wait_for('await_trial_confirmation',['continue_geometry'])
            self.update(stage='reconstructing_geometry',progress=47)
            with self.timing.span('reconstruction'):
                summary=reconstruct(self.p,self.check)
            self.timing.flush(); self.update(summary=summary,geometry_available=True,progress=50)
            passed=bool(closure_passes(summary['closure']))
            summary.update(closure_check_passed=passed,closure_limit_mm=1.0,absolute_accuracy_validated=False)
            write_json(self.p/'fine_summary.json',summary)
            self.update(summary=summary,closure_check_passed=passed)
            if not passed:
                self.update(scan_valid=False)
                raise RuntimeError('首尾轮廓复核未通过；本轮几何仅作诊断，停止并禁止进入颜色扫描。')
            action=self.wait_for('await_laser_off',['laser_off','finish_geometry'])
            if action=='laser_off':
                color_start=self.pos()
                if abs(color_start-(start-360))>.35: raise RuntimeError('Turntable moved between geometry and color')
                self.settings(70,8); color=self.p/'color'; color.mkdir()
                for i in range(181):
                    if i: motion=self.move_to(i,color_start,color)
                    else: motion=dict(before=color_start,after=color_start,pulses=0)
                    self.update(phase='color',stage='capturing_color',index=i)
                    pair,counters=self.pair(color,f'position{i:03d}','color')
                    after=self.verify(motion['after'],8)
                    write_json(color/f'position{i:03d}_record.json',dict(status='captured_and_verified',motion=motion,frame_counters=counters))
                    self.update(completed_positions=i+1,angle=after,progress=round(50+(i+1)/181*45,1),pending_index=None)
                self.update(stage='mapping_color',progress=97)
                with self.timing.span('color_mapping'):colorize(self.p,self.check)
                self.update(real_color=True)
            self.check(); self.verify(self.angle,self.state['led'])
            self.update(stage='verifying_result',progress=98)
            from quality import finalize
            with self.timing.span('audit_and_archive'):audit,archive=finalize(self.p,self.check)
            summary=json.loads((self.p/'fine_summary.json').read_text())
            summary['completion_verification']=audit;write_json(self.p/'fine_summary.json',summary)
            self.update(completion_verification=audit,archive=archive,quality_status=audit['status'],quality_warning=None if audit['passed'] else '采集计算已完成，但部分质量检查未通过，请查看核验报告。')
            self.update(status='completed',stage='completed',progress=100,expected_actions=[])
        except BaseException as exc:
            self.cancel.set()
            if self.monitor: self.stopped.wait(18)
            verified=self.state.get('stop_verified',False)
            self.update(status=('stopped' if isinstance(exc,Cancelled) else 'failed') if verified else 'stop_unverified',stage='ended',error=str(exc),expected_actions=[])
            if not isinstance(exc,Cancelled): raise
        finally:
            self.timing.flush()
            self.finished.set()
            if self.monitor: self.monitor.join(timeout=1)
            if self.bridge and (not self.monitor or not self.monitor.is_alive()): self.bridge.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--scan',type=Path,required=True); args=parser.parse_args()
    scan=Scan(args.scan)
    signal.signal(signal.SIGTERM,lambda *_:scan.cancel.set())
    signal.signal(signal.SIGINT,lambda *_:scan.cancel.set())
    scan.run()
