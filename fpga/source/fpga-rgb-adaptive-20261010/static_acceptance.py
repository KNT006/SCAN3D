"""Static A/B/color regression and timing, never issues movement commands."""
from pathlib import Path
import sys,time,json,inspect,hashlib
H=Path(__file__).resolve().parent
mode=sys.argv[1];count=int(sys.argv[2]);assert mode in ('baseline','sequential','overlap','production')
manifest=json.loads((H/'host-candidate-manifest.json').read_text())
assert all(hashlib.sha256((H/'fpga'/n).read_bytes()).hexdigest()==v for n,v in manifest.items()),'Staged host changed'
sys.path[:0]=([str(H/'fpga')] if mode not in ('baseline','production') else [])+['/opt/afc03-scanner/fpga','/opt/afc03-motor','/opt/afc03-scanner/vendor']
import cv2;cv2.setNumThreads(2)
from stationary_strategy import acquire,PORT,motor_state,unchanged
from rk_motor import MotorBridge
from scan_pipeline import ScanPipeline
root=Path('/userdata/afc03-scanner/jobs/rgb-adaptive-20261010')/(mode+'-'+str(time.monotonic_ns()))
root.mkdir(parents=True,exist_ok=False)
def state():
 b=MotorBridge(PORT)
 try:return motor_state(b)
 finally:b.close()
before=state();results=[];pipeline=ScanPipeline();started=time.monotonic()
def retire(wait=False):
 r=pipeline.retire(wait)
 if r:
  results.append(dict(folder=str(r['folder']),report=r['report'],storage_seconds=r['storage_seconds']))
  print(json.dumps(dict(position=len(results),seconds=r['report']['acquisition_seconds'],passed=r['report']['passed'])),flush=True)
try:
 for i in range(count):
  while len(pipeline.pending)>=pipeline.capacity:retire(True)
  while pipeline.pending and pipeline.pending[0]['stored'].done():retire()
  args=dict(expected_motor=before,color_led=8,timing_profile='fast',verify_pixels=i in (0,count-1),pipeline=pipeline)
  if mode!='baseline':args['overlap_enabled']=mode in ('overlap','production')
  acquire(root/f'position-{i:03d}',H/'acceptance-bundle',i in (0,count-1),**args)
 while pipeline.pending:retire(True)
finally:
 try:pipeline.close()
 finally:
  b=MotorBridge(PORT)
  try:b.send('LASER OFF');b.send('LED 0');after=motor_state(b);unchanged(before,after)
  finally:b.close()
report=dict(passed=True,mode=mode,count=count,seconds=time.monotonic()-started,
 before=before,after=after,results=results,rejected=[str(p) for p in root.glob('position-*/*rejected*/report.json')])
(root/'summary.json').write_text(json.dumps(report,indent=2));(H/('static-'+mode+'.json')).write_text(json.dumps(dict(path=str(root),**report),indent=2))
print(json.dumps(dict(summary=str(root/'summary.json'),passed=True,seconds=report['seconds'],retries=len(report['rejected']))),flush=True)
