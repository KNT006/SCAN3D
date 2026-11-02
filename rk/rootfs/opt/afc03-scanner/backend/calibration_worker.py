"""Explicit-command calibration capture. Idle sessions never move automatically."""
import argparse
import json
from pathlib import Path
import signal
import sys
import threading
import uuid
import cv2
import numpy as np
from live_worker import Scan,Cancelled,PORT
from live_geometry import write_json
from calibration_math import detect,read,solve_session

class Calibration(Scan):
    def wait_command(self):
        token=uuid.uuid4().hex
        self.update(status='waiting',stage='calibration_ready',token=token)
        request=self.p/'action.request'
        while True:
            self.sleep(.1)
            if request.exists():
                data=read(request);request.unlink()
                if data.get('token')!=token:raise RuntimeError('标定页面已过期，请刷新')
                self.update(status='running',stage='calibration_'+data['action'],token=None)
                return data

    def connect(self):
        if self.bridge:return
        sys.path.insert(0,str(Path(__file__).parent/'hardware'))
        from rk_motor import MotorBridge
        self.bridge=MotorBridge(PORT)
        self.monitor=threading.Thread(target=self.monitor_stop,daemon=True);self.monitor.start()

    def capture(self,request):
        kind=self.cfg['kind'];stage=request.get('stage','pattern');held=request['held_out'];ident=uuid.uuid4().hex[:12]
        self.connect()
        if kind=='laser' and stage not in ('pattern','background','laser_on'):raise ValueError('无效激光阶段')
        pending=read(self.p/'pending_pose.json') if (self.p/'pending_pose.json').exists() else None
        expected='pattern' if pending is None else ('background' if 'background' not in pending else 'laser_on')
        if kind=='laser' and stage!=expected:raise ValueError('请依次采棋盘格、关激光背景、开激光照片')
        if kind!='laser':stage='pattern'
        if request['laser_on']!=(stage=='laser_on'):raise ValueError('激光状态确认与采集阶段不符')
        # Settings are held for the lifetime of this worker, not reopened between frames.
        self.settings(70 if stage=='pattern' else 10,8 if stage=='pattern' else 0)
        before=None
        if kind=='axis':
            if self.send('ENSTATE')!='OK ENSTATE 1':raise RuntimeError('转轴标定需要驱动器已使能')
            values=[]
            for _ in range(3):values.append(self.pos());self.sleep(.2)
            if np.ptp(values)>.06:raise RuntimeError('电机未停稳')
            before=values[-1];self.angle=before
        # Pair checks preserve bad attempts and retry frames only, never movement.
        pair,counters=self.pair(self.p,ident,stage)
        if kind=='axis' and abs(self.pos()-before)>.06:raise RuntimeError('拍摄时编码器发生变化')
        filename=f'{ident}_{stage}.png'
        entry=dict(id=ident,held_out=held,frame_counters=counters,pattern=filename)
        if stage=='pattern':
            raw=cv2.imread(str(self.p/filename));corners,image=detect(raw,self.cfg)
            if kind=='axis' and self.records:
                ref=np.array(self.records[-1]['corners'])
                if np.linalg.norm(corners[::-1]-ref,axis=1).mean()<np.linalg.norm(corners-ref,axis=1).mean():corners=corners[::-1].copy()
            entry['corners']=corners.tolist()
            if kind=='axis':entry['angle']=before
            cv2.drawChessboardCorners(image,tuple(self.cfg['pattern']),corners.astype(np.float32).reshape(-1,1,2),True)
            cv2.imwrite(str(self.p/'corners.jpg'),cv2.resize(image,(540,960)))
        if kind=='laser':
            if stage=='pattern':pending=entry
            else:pending[stage]=filename
            write_json(self.p/'pending_pose.json',pending)
            if stage=='laser_on':
                # Validate this pose immediately; keep its originals if it needs review.
                from calibration_math import laser_intersection
                _,metrics=laser_intersection(self.p,pending,self.cfg,read(self.p/'camera.json'))
                pending['metrics']=metrics;self.records.append(pending);(self.p/'pending_pose.json').unlink()
                pending=None
        else:self.records.append(entry)
        write_json(self.p/'captures.json',self.records)
        self.update(captures=len(self.records),training=sum(not r['held_out'] for r in self.records),held_out=sum(r['held_out'] for r in self.records),next_stage=('pattern' if pending is None else ('background' if 'background' not in pending else 'laser_on')),last_error=None,angle=before if before is not None else self.angle)

    def move(self):
        if self.cfg['kind']!='axis':raise ValueError('仅转轴标定支持点动')
        self.connect()
        if not self.records:raise ValueError('先采原位，再点动')
        start=self.records[0]['angle'];index=self.state.get('move_count',0)+1
        if index>6:raise ValueError('本轮已达到 90° 点动上限，请结束并检查采集姿态')
        before=self.pos()
        if self.angle is None:self.angle=before
        if abs(before-self.angle)>.06 or self.send('ENSTATE')!='OK ENSTATE 1':raise RuntimeError('位置变化或电机未使能')
        pulses=round(index*3200/24)-round((index-1)*3200/24)
        journal=self.p/f'move{index:03d}.json'
        if journal.exists():raise RuntimeError('该移动已记账，禁止重发')
        motion=dict(before=before,pulses=pulses,status='reserved_no_retry');write_json(journal,motion)
        # Once reserved, any error terminates the session; no retry button can resend it.
        with self.io:
            self.check();motion['ack']=self.bridge.move(pulses,10)
        motion['status']='dispatched';write_json(journal,motion)
        values=[]
        for _ in range(50):
            self.sleep(.3);values.append(self.pos())
            if len(values)>=3 and np.ptp(values[-3:])<.06 and abs(values[-1]-before)>1:break
        if len(values)<3 or np.ptp(values[-3:])>=.06 or abs(values[-1]-start+round(index*3200/24)*360/3200)>.35:raise RuntimeError('点动停稳或角度检查失败')
        self.sleep(1);self.angle=values[-1]
        if abs(self.pos()-self.angle)>.06:raise RuntimeError('停稳后角度漂移')
        motion.update(after=self.angle,status='settled');write_json(journal,motion)
        self.update(move_count=index,angle=self.angle)

    def run(self):
        self.records=read(self.p/'captures.json')
        try:
            while True:
                cmd=self.wait_command();action=cmd['action']
                if action=='finish':
                    self.update(status='completed',stage='calibration_saved',token=None);break
                if action=='solve':
                    try:
                        result=solve_session(self.p)
                        write_json(self.p/('solve-'+uuid.uuid4().hex+'.json'),result)
                        write_json(self.p/'result.json',result)
                        if result['passed']:
                            self.update(status='completed',stage='calibration_solved',result=result,token=None,last_error=None);break
                        self.update(result=result,last_error='内部检查未通过，可补充姿态后重新计算，或保存并结束。');continue
                    except (ValueError,cv2.error) as exc:
                        self.update(last_error=str(exc));continue
                if action=='move':self.move();continue
                if action=='discard_pose':
                    pending=self.p/'pending_pose.json'
                    if pending.exists():pending.rename(self.p/('discarded-'+uuid.uuid4().hex+'.json'))
                    self.update(next_stage='pattern',last_error=None);continue
                if action!='capture':raise RuntimeError('未知标定操作')
                try:self.capture(cmd)
                except (ValueError,cv2.error) as exc:self.update(last_error=str(exc))
        except BaseException as exc:
            self.cancel.set()
            if self.monitor:self.stopped.wait(18)
            self.update(status='stopped' if isinstance(exc,Cancelled) else 'failed',stage='ended',error=str(exc),token=None,stop_verified=self.state.get('stop_verified') if self.bridge else None)
            if not isinstance(exc,Cancelled):raise
        finally:
            self.timing.flush()
            self.finished.set()
            if self.monitor:self.monitor.join(timeout=1)
            if self.bridge and (not self.monitor or not self.monitor.is_alive()):self.bridge.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--session',type=Path,required=True);args=parser.parse_args()
    worker=Calibration(args.session)
    signal.signal(signal.SIGTERM,lambda *_:worker.cancel.set());signal.signal(signal.SIGINT,lambda *_:worker.cancel.set())
    worker.run()
