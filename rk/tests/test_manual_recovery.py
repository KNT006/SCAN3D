"""Mocked manual recovery and STOP semantics; never opens hardware."""
import importlib.util,sys,types,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
stub=types.ModuleType('stationary_strategy');stub.motor_state=lambda b:b.state;stub.write=lambda p,o:None
sys.modules['stationary_strategy']=stub
spec=importlib.util.spec_from_file_location('motion',Path(__file__).parents[1]/'rootfs/opt/afc03-scanner/scan3d/motion.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Bridge:
 def __init__(self,**kw):self.state=dict(session=8,emitted=500,moving=0,pending=0,armed=0,count_known=0,fault='stopped',**kw);self.commands=[]
 def send(self,c):
  self.commands.append(c)
  if c.startswith('PULSE_ZERO'):self.state.update(emitted=0,count_known=1,fault='none')
  if c=='PULSE_STATE':return 'OK PULSE_STATE '+' '.join(f'{k}={v}' for k,v in self.state.items())
  return 'OK'
class Tests(unittest.TestCase):
 def test_unknown_stop_manual_recovery(self):
  b=Bridge();r=m.recover_manual_reference(b);self.assertTrue(r['reset']);self.assertEqual(b.commands,['PULSE_STATE','PULSE_ZERO 8','PULSE_STATE']);self.assertTrue(r['scan_resume_invalidated'])
 def test_known_stopped_no_reset(self):
  b=Bridge();b.state.update(count_known=1,fault='none');r=m.recover_manual_reference(b);self.assertFalse(r['reset']);self.assertNotIn('PULSE_ZERO 8',b.commands)
 def test_fault_or_moving_rejected(self):
  for field,value in [('moving',1),('pending',2),('armed',1),('fault','host_timeout'),('fault','rmt_error')]:
   b=Bridge();b.state[field]=value
   with self.assertRaises(ValueError):m.recover_manual_reference(b)
   self.assertEqual(b.commands,['PULSE_STATE'])
 def test_changed_session_after_zero_rejected(self):
  b=Bridge();original=b.send
  def send(c):
   result=original(c)
   if c.startswith('PULSE_ZERO'):b.state['session']=9
   return result
  b.send=send
  with self.assertRaises(ValueError):m.recover_manual_reference(b)
 def test_explicit_stop_while_state_request_inflight(self):
  b=Bridge();b.state.update(count_known=1,fault='none');stopped=False;original=b.send;written=[]
  def send(c):
   nonlocal stopped
   if c=='PULSE_STATE':stopped=True;b.state.update(count_known=0,fault='stopped')
   return original(c)
  b.send=send
  def check():
   if stopped:raise m.MotionStopped('operator')
  with tempfile.TemporaryDirectory() as tmp,patch.object(m,'write',lambda p,o:written.append(o)),patch.object(m.time,'sleep',lambda _:None):
   with self.assertRaises(m.MotionStopped):m.move_once(b,dict(b.state),100,40,Path(tmp)/'move.json',check)
  self.assertEqual(written[-1]['status'],'operator_stopped');self.assertIn('STOP',b.commands)
if __name__=='__main__':unittest.main()
