import importlib.util,tempfile,json,unittest,ast,types
from pathlib import Path
import numpy as np
spec=importlib.util.spec_from_file_location('resume',Path(__file__).parents[1]/'rootfs/opt/afc03-scanner/scan3d/scan_resume.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class ResumeTests(unittest.TestCase):
 def test_guard_and_skip(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);s=dict(mode='scan3d',status='paused',boot_id='boot',planned_intervals=60,initial_motor=dict(session=7,emitted=100),final_motor=dict(session=7,emitted=153,count_known=1))
   for i in range(1):
    q=p/f'position-{i:03d}';q.mkdir();(q/'status.json').write_text(json.dumps(dict(status='complete')))
    for label in ['A','B']:
     d=q/label;d.mkdir();(d/'frame.json').write_text(json.dumps(dict(angle=dict(emitted_after=100))));np.savez(d/'points.npz',axis_frame_mm=np.zeros((1,3)),rgb=np.zeros((1,3)))
   motor=dict(session=7,emitted=153,count_known=1,moving=0,pending=0)
   r=m.plan_resume(p,s,motor,'boot');self.assertEqual(r['start'],1);self.assertTrue(r['skip_move'])
   s['final_motor']['emitted']=100;motor['emitted']=100;self.assertFalse(m.plan_resume(p,s,motor,'boot')['skip_move'])
   s['final_motor']['emitted']=125;motor['emitted']=125;self.assertEqual(m.plan_resume(p,s,motor,'boot')['current'],125)
   for changes in [dict(session=8),dict(emitted=154),dict(moving=1),dict(count_known=0)]:
    with self.assertRaises(ValueError):m.plan_resume(p,s,dict(motor,**changes),'boot')
   with self.assertRaises(ValueError):m.plan_resume(p,s,motor,'reboot')
class RunnerMovementTests(unittest.TestCase):
 def test_actual_runner_movement_branch(self):
  source=Path(__file__).parents[1]/'rootfs/opt/afc03-scanner/scan3d/runner.py'
  tree=ast.parse(source.read_text(encoding='utf-8'))
  loop=next(n for n in ast.walk(tree) if isinstance(n,ast.For) and isinstance(n.target,ast.Name) and n.target.id=='index' and isinstance(n.iter,ast.Call) and any(isinstance(a,ast.Name) and a.id=='first' for a in n.iter.args))
  branch=next(n for n in loop.body if isinstance(n,ast.If) and isinstance(n.test,ast.BoolOp))
  code=compile(ast.Module(body=[branch],type_ignores=[]),str(source),'exec')
  class Bridge:
   def close(self):pass
  for emitted,skip,delta in [(100,False,53),(125,False,28),(153,True,0)]:
   calls=[]
   def require(value,message):
    if not value:raise ValueError(message)
   ctx=dict(index=1,first=1,resume=True,skip_first_move=skip,plan=dict(current=emitted),state={},output=Path('/unused'),write=lambda *a:None,
    MotorBridge=lambda _:Bridge(),PORT='mock',motor_state=lambda _:dict(session=7,emitted=emitted),session=7,origin=100,INTERVALS=60,
    require=require,move_once=lambda b,before,d,*args:calls.append(d),tuning=dict(rate_pps=120,motor_settle=0),check=lambda:None,time=types.SimpleNamespace(sleep=lambda _:None,time_ns=lambda:1))
   exec(code,ctx);self.assertEqual(calls,[] if skip else [delta])
if __name__=='__main__':unittest.main()
