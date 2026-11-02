"""Local UNIX control broker; fixed operations only, shared hardware lock, no shell input."""
import sys,os,socketserver,socket,json,threading,subprocess,time,uuid,fcntl,grp,signal
from pathlib import Path
from contextlib import contextmanager
from chat_priority import reserve as chat_reservation
sys.path[:0]=['/opt/afc03-scanner/scan3d','/opt/afc03-scanner/fpga','/opt/afc03-motor']
from common import *
from stationary_strategy import PORT,motor_state
from rk_motor import MotorBridge
from motion import move_once,MotionStopped,recover_manual_reference
from cleanup import Cleanup
from run_access import acquire as acquire_run
from manual_laser import ManualLaser
from manual_session import ManualSession
from spatial_filter import validate as spatial_validate,DEFAULT as SPATIAL_DEFAULT
cleanup=Cleanup(DATA,Path('/opt/afc03-scanner/frontend/dist/results'))
cleanup_mutex=threading.Lock()
mutex=threading.Lock();process=None;current=None;manual_stop=threading.Event()
manual_gate=threading.RLock()
manual_session=ManualSession(lambda:MotorBridge(PORT))
@contextmanager
def hardware():
 if not mutex.acquire(False):raise ValueError('设备正在执行操作')
 try:
  if active() or (process and process.poll() is None):raise ValueError('扫描或采集正在运行')
  with chat_reservation(), open('/run/lock/afc03-fpga-scan.lock','a') as f:
   fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
   from rk_rgb_roi_diag import scanner_idle
   scanner_idle('http://127.0.0.1:8081')
   yield
 finally:mutex.release()
def bridge_cmd(cmd):
 return manual_session.send(cmd)
manual_laser=ManualLaser(bridge_cmd)
def renew_manual_laser():
 while True:
  time.sleep(5)
  renew_once()

def renew_once():
 with manual_gate:
  # Motion holds the hardware lock, so use its existing broker connection.
  if manual_session.bridge is not None:
   if not manual_stop.is_set():manual_laser.renew()
   return
  if not manual_laser.status()['continuous'] or not mutex.acquire(False):return
  try:
   if active() or (process and process.poll() is None):
    manual_laser.clear();return
   with open('/run/lock/afc03-fpga-scan.lock','a') as f:
    try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
     manual_laser.clear();return
    manual_laser.renew()
  except Exception:
   manual_laser.clear()
  finally:mutex.release()
def handle(d):
 global process,current
 op=d.get('op')
 if op=='status':return dict(active=active().name if active() else None,worker_running=bool(process and process.poll() is None),last_job=current,manual_motion=manual_session.bridge is not None,manual_laser=manual_laser.status())
 if op=='spatial_profile':return spatial_validate(read(DATA/'scan3d-work/spatial-profile.json',SPATIAL_DEFAULT))
 if op=='controls':
  raw=subprocess.check_output(['v4l2-ctl','-d',camera_device(),'--list-ctrls'],text=True)
  return dict(camera_controls=raw)
 if op=='stop':
  manual_stop.set();p=active()
  if p:(p/'STOP').touch()
  if current and process and process.poll() is None:(DATA/current/'STOP').touch()
  with manual_gate:
   manual_laser.clear()
   result=bridge_cmd('STOP');manual_laser.lights('OFF',0)
  return dict(message='已发送停止，激光与灯带关闭',reply=result)
 if op=='lights':
  with manual_gate:
   def apply():return manual_laser.lights(d.get('laser'),d.get('led'),d.get('laser_a'),d.get('laser_b'))
   if manual_session.bridge is not None:
    if manual_stop.is_set():raise ValueError('转盘正在停止，请等待停止完成')
    return apply()
   with hardware():return apply()
 if op in ('cleanup_preview','cleanup_execute'):
  # File maintenance on another run must not acquire or stop the hardware.
  with cleanup_mutex:
   name=d.get('name');fd=acquire_run(name,exclusive=True)
   try:
    p=active()
    if (p and p.name==name) or (current==name and process and process.poll() is None):raise ValueError('不能删除正在扫描或采集的数据')
    if op=='cleanup_preview':return cleanup.preview(name,d.get('mode'))
    return cleanup.execute(name,d.get('mode'),d.get('token'),d.get('confirm'),d.get('acknowledged'))
   finally:os.close(fd)
 with hardware():
  if op=='save_spatial':
   cfg=spatial_validate(d.get('profile'));cfg.pop('axis_sha256',None)
   target=DATA/'scan3d-work/spatial-profile.json';target.parent.mkdir(exist_ok=True)
   tmp=target.with_suffix('.tmp');tmp.write_text(json.dumps(cfg),encoding='utf-8');os.replace(tmp,target)
   return dict(saved=True,profile=cfg)
  if op=='camera':
   gain=d.get('gain')
   if type(gain)!=int or not 0<=gain<=240:raise ValueError('增益需在已验证范围 0–240')
   subprocess.run(['v4l2-ctl','-d',camera_device(),'--set-ctrl=gain='+str(gain)],check=True)
   return dict(readback=subprocess.check_output(['v4l2-ctl','-d',camera_device(),'--get-ctrl=gain'],text=True))
  if op=='recover_manual_motion':
   if d.get('ready') is not True:raise ValueError('请确认只恢复手动转动，放弃原角度参考；旧扫描不能继续')
   with manual_gate:manual_session.open()
   try:
    result=recover_manual_reference(manual_session)
    manual_stop.clear()
    audit=DATA/'scan3d-controls';audit.mkdir(exist_ok=True)
    (audit/('manual-reference-'+uuid.uuid4().hex+'.json')).write_text(json.dumps(result))
    return dict(message='手动转动已恢复，角度参考已重新建立；旧扫描不能续接',**result)
   finally:
    with manual_gate:manual_session.close()
  if op=='move':
   angle=d.get('angle');rate=d.get('rate',40)
   if not isinstance(angle,(float,int)) or isinstance(angle,bool) or not .1125<=abs(angle)<=360:raise ValueError('角度范围为 ±0.1125°～360°')
   if rate not in (40,120):raise ValueError('无效速度')
   delta=round(angle/.1125);manual_stop.clear();log=DATA/'scan3d-controls';log.mkdir(exist_ok=True)
   with manual_gate:manual_session.open()
   b=manual_session
   try:
    before=motor_state(b)
    def check():
     if manual_stop.is_set():raise MotionStopped('用户停止转动')
    after=move_once(b,before,delta,rate,log/(uuid.uuid4().hex+'.json'),check)
    return dict(actual_commanded_degrees=delta*.1125,after=after)
   except MotionStopped:
    return dict(stopped=True,message='已停止；若脉冲计数未知，请恢复手动转动后重新操作')
   finally:
    with manual_gate:b.close()
  if op=='resume':
   if d.get('ready') is not True:raise ValueError('请确认物品、相机和转盘未移动且驱动保持供电')
   name=d.get('name');output=job(name);checkpoint=read(output/'status.json')
   from scan_resume import plan_resume
   b=MotorBridge(PORT)
   try:plan_resume(output,checkpoint,motor_state(b),Path('/proc/sys/kernel/random/boot_id').read_text().strip())
   finally:b.close()
   request=DATA/'scan3d-controls';request.mkdir(exist_ok=True)
   cfgfile=request/(name+'-resume.json')
   cfgfile.write_text(json.dumps(dict(step=checkpoint['requested_step_deg'],title=checkpoint.get('title',checkpoint.get('object_name',name)))))
   log=open(request/(name+'-resume.log'),'ab')
   process=subprocess.Popen(['/usr/bin/python3',str(CODE/'runner.py'),'--output',str(output),'--request',str(cfgfile),'--mode','scan','--resume'],stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=True);log.close();current=name
   return dict(id=name,status='starting')
  if op in ('scan','capture'):
   from datetime import datetime
   name='scan3d-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
   cfg=dict(step=d.get('step',6),title=str(d.get('title','新扫描'))[:80],timing_profile='fast')
   if cfg['step'] not in (.1125,.45,2,6):raise ValueError('无效步长')
   if op=='scan' and d.get('ready') is not True:raise ValueError('请确认物体固定、支架未动、驱动供电')
   import shutil
   from storage_budget import startup
   budget=startup(cfg['step'],op);required=budget['required_bytes'];free=shutil.disk_usage(DATA).free
   if free<required:raise ValueError(f'存储空间不足：当前可用 {free/1024**3:.1f} GiB，预计需要约 {required/1024**3:.1f} GiB（{budget["positions"]} 个位置，其中 {budget["retained_positions"]} 组保留图片；含余量），请先归档或接入存储')
   cfg['startup_storage_budget']=budget
   manual_laser.clear(off=True)
   request=DATA/'scan3d-controls';request.mkdir(exist_ok=True);cfgfile=request/(name+'.json');cfgfile.write_text(json.dumps(cfg))
   log=open(request/(name+'.log'),'wb')
   process=subprocess.Popen(['/usr/bin/python3',str(CODE/'runner.py'),'--output',str(DATA/name),'--request',str(cfgfile),'--mode',op],stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=True);log.close();current=name
   return dict(id=name,status='starting')
 raise ValueError('未知操作')
class Handler(socketserver.StreamRequestHandler):
 def handle(self):
  self.connection.settimeout(120)
  try:
   line=self.rfile.readline(8193)
   if len(line)>8192:raise ValueError('请求过大')
   result=dict(ok=True,result=handle(json.loads(line)))
  except Exception as e:
   import traceback
   traceback.print_exc() # Keep original diagnostic details in the service journal.
   result=dict(ok=False,error=str(e))
  self.wfile.write(json.dumps(result).encode()+b'\n')
if __name__=='__main__':
 path='/run/afc03-scan3d.sock'
 try:os.unlink(path)
 except FileNotFoundError:pass
 server=socketserver.ThreadingUnixStreamServer(path,Handler);server.daemon_threads=True
 os.chown(path,0,grp.getgrnam('afcscanner').gr_gid);os.chmod(path,0o660)
 threading.Thread(target=renew_manual_laser,daemon=True,name='manual-laser-hold').start()
 server.serve_forever()
