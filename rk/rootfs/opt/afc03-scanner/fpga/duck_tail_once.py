
import sys,json,os,time,fcntl,shutil,signal
from pathlib import Path
import cv2
from stationary import acquire,motor_state,write,PORT
from pilot import move_once
from rk_motor import MotorBridge
from row_results import require
from scan_storage import compress_position
from full_scan import closure,merge
out=Path(sys.argv[1]);assert out.resolve()==Path('/userdata/afc03-scanner/jobs/fpga-full-20261003-005504')
lock=open('/run/lock/afc03-fpga-scan.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(KeyboardInterrupt()))
state=json.loads((out/'status.json').read_text());assert state['status']=='paused' and state['last_index']==793 and state['completed_positions']==794
assert not (out/'tail-resume-1.json').exists(),'Reserved already; never retry motion'
b=MotorBridge(PORT)
try:
 now=motor_state(b);assert now['session']==218030000 and now['emitted']==3176 and now['physical_enable']=='commanded_1',now
 b.send('LASER OFF');b.send('LED 0')
finally:b.close()
oldmove=json.loads((out/'move-794.json').read_text());assert oldmove['status']=='pulse_sequence_complete' and oldmove['after']['emitted']==3176
write(out/'status-before-tail-resume.json',state)
failed=out/'position-794';archived=out/'failed-position-794-original'
assert not archived.exists() and failed.is_dir();failed.rename(archived)
write(out/'tail-resume-1.json',dict(status='reserved_no_retry',user_confirmed_scene_unchanged=True,expected_motor=now,reacquire_index=794,remaining_moves=6,remaining_degrees=2.7))
start=time.perf_counter();prior_elapsed=state['elapsed_seconds']
state.update(status='running',phase='reacquiring_current_position',pid=os.getpid(),tail_resume=True)
state.pop('error',None);write(out/'status.json',state)
def check():
 require(not(out/'STOP').exists(),'Operator stop');require(shutil.disk_usage(out).free>1024**3,'Disk reserve')
try:
 for i in range(794,801):
  check()
  if i>794:
   b=MotorBridge(PORT)
   try:
    before=motor_state(b);require(before['session']==218030000 and before['emitted']==4*(i-1),'Position changed')
    state.update(phase='moving',target_index=i);write(out/'status.json',state)
    move_once(b,before,4,40,out/f'move-{i:03d}.json',check)
   finally:b.close()
   time.sleep(.6)
  state['phase']='acquiring';write(out/'status.json',state)
  folder=out/f'position-{i:03d}'
  report=acquire(folder,out/'bundle',False,zero_pulses=0,expected_motor=dict(session=218030000,emitted=i*4),external_check=check,scan_lock_owned=True,color_led=8)
  for label in 'AB':
   h=json.loads((folder/label/'frame.json').read_text());require(h['angle']['emitted_after']==i*4,'Angle mismatch');require(h['stream_epoch']=='17c1ea5a560746fb93179b21b250fd25','Camera restarted')
   state['retained_points'][label]+=report['lasers'][label]['retained_points']
  state['stored_bytes']+=compress_position(folder)
  for f in folder.glob('*/report.json'):
   r=json.loads(f.read_text());state['capture_retries']+=max(0,r.get('capture_attempts',1)-1)
  state.update(last_index=i,completed_positions=i+1,commanded_degrees=i*.45,lasers=report['lasers'],color=report['color'],elapsed_seconds=prior_elapsed+time.perf_counter()-start)
  write(out/'status.json',state);print(json.dumps(dict(index=i,angle=i*.45)),flush=True)
 state['phase']='closure_check';write(out/'status.json',state);state['closure']=closure(out);write(out/'status.json',state)
 if state['closure']['passed']:
  state['model_points']=merge(out,range(800));state.update(status='complete',phase='complete',passed=True)
 else:state.update(status='paused',phase='stopped',passed=False,error='Full-turn image closure failed; all images preserved')
except BaseException as e:
 state.update(status='paused',phase='stopped',passed=False,error=type(e).__name__+': '+str(e));raise
finally:
 b=MotorBridge(PORT)
 try:b.send('STOP');b.send('LASER OFF');b.send('LED 0');state['final_motor']=motor_state(b)
 finally:b.close()
 state['elapsed_seconds']=prior_elapsed+time.perf_counter()-start;state['resume_active_seconds']=time.perf_counter()-start;state['estimated_remaining_seconds']=0 if state['last_index']==800 else None;write(out/'status.json',state)
 write(out/'tail-resume-1.json',dict(status='completed' if state['last_index']==800 else 'stopped',final_motor=state['final_motor'],last_index=state['last_index'],closure=state.get('closure')))
print(json.dumps({'status':state['status'],'closure':state.get('closure')}),flush=True)
