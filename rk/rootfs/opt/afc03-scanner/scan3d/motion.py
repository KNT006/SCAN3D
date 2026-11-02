import time,math
from stationary_strategy import motor_state,write
class MotionStopped(Exception):
 """An explicit operator STOP; not successful completion or a device fault."""

def recover_manual_reference(bridge):
 # Only an explicit manual recovery may discard the uncertain angular reference.
 def raw():
  d=dict(x.split('=',1) for x in bridge.send('PULSE_STATE').split()[2:] if '=' in x)
  for k in ('session','emitted','moving','pending','count_known','armed'):d[k]=int(d[k])
  return d
 before=raw()
 if before['moving'] or before['pending'] or before['armed'] or before.get('fault') not in ('none','disabled','stopped'):
  raise ValueError('控制器仍在运动或存在真实故障，不能重设手动参考')
 if before['count_known']==1:return dict(reset=False,before=before,after=before)
 if before.get('fault')!='stopped':raise ValueError('只有主动停止造成的位置未知可以恢复手动参考')
 ack=bridge.send('PULSE_ZERO '+str(before['session']))
 after=raw()
 if after['session']!=before['session'] or after['count_known']!=1 or after['emitted']!=0 or after['moving'] or after['pending'] or after['armed'] or after.get('fault')!='none':
  raise ValueError('手动参考恢复校验失败，不能转动')
 return dict(reset=True,before=before,after=after,ack=ack,scan_resume_invalidated=True)

def move_once(bridge,before,delta,rate,journal,check):
 if journal.exists():raise ValueError('运动日志已存在，禁止重放')
 if type(delta)!=int or not 1<=abs(delta)<=3200 or rate not in (40,120):raise ValueError('无效脉冲运动')
 start=time.monotonic();check();write(journal,dict(status='reserved_no_retry',before=before,delta=delta))
 try:
  bridge.send('PULSE_ARM '+str(before['session']))
  ack=bridge.send(f'PULSE_MOVE {delta} {rate} {before["session"]}')
  write(journal,dict(status='dispatched',before=before,delta=delta,ack=ack));deadline=time.monotonic()+abs(delta)/rate+6
  while True:
   check();time.sleep(.04)
   d=dict(x.split('=',1) for x in bridge.send('PULSE_STATE').split()[2:] if '=' in x)
   check() # STOP may arrive while the state request is in flight.
   if int(d['session'])!=before['session'] or int(d['count_known'])!=1 or d['fault']!='none':raise ValueError('控制器状态变化；不重试运动')
   if not int(d['moving']):break
   if time.monotonic()>deadline:raise TimeoutError('转动超时；不重试')
  if int(d['pending']) or int(d['emitted'])!=before['emitted']+delta:raise ValueError('完成脉冲数不符')
  bridge.send('PULSE_DISARM');after=motor_state(bridge)
  write(journal,dict(status='pulse_sequence_complete',before=before,after=after,delta=delta,physical_motion_verified=False,rate_pps=rate,elapsed_seconds=time.monotonic()-start));return after
 except BaseException as e:
  try:bridge.send('STOP')
  except Exception:pass
  write(journal,dict(status='operator_stopped' if isinstance(e,MotionStopped) else 'failed_no_retry',before=before,delta=delta,error=str(e)))
  raise
