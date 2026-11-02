"""Opt-in hardware qualification. No laser, motor or Flash controls."""
import argparse,json,time,dataclasses,fcntl
from pathlib import Path
from contextlib import ExitStack
from role_client import RoleClient,BackgroundIdentity,DiagnosticError
from role_capture import BackgroundMMIO,capture
from rk_rgb_roi_diag import Probe,CameraAPI,scanner_idle,parse_ppm
from job_client import JobClient

def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['inspect','capture','process']);p.add_argument('--role',type=int,choices=[0,1,2]);p.add_argument('--operator-confirmed',action='store_true');p.add_argument('--output',type=Path);p.add_argument('--off-dir',type=Path);p.add_argument('--on-dir',type=Path);p.add_argument('--epoch',type=int,default=20261002)
 p.add_argument('--roi-x0',type=int,help='Optional aligned start of the 32-column diagnostic ROI; thresholds unchanged')
 a=p.parse_args()
 if a.action=='capture' and (not a.operator_confirmed or a.role is None or a.output is None):p.error('capture requires explicit operator state, role and output')
 if a.action=='process' and (a.role not in [1,2] or not a.off_dir or not a.on_dir or not a.output):p.error('process requires role, exact frame directories and output')
 with ExitStack() as stack:
  for name in ['afc03-ddr-diag.lock','afc03-rgb-roi-diag.lock']:
   fd=stack.enter_context(open('/run/lock/'+name,'a'));fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  scanner_idle('http://127.0.0.1:8081');probe=Probe();stack.callback(probe.close);mmio=BackgroundMMIO(probe)
  if a.action=='inspect':
   print(json.dumps({str(role):dataclasses.asdict(RoleClient(mmio.read,mmio.write,role=role).snapshot()) for role in [0,1]},default=str));return
  if a.action=='capture':
   report=capture(probe,RoleClient(mmio.read,mmio.write,role=a.role,poll_seconds=0),CameraAPI(),a.output,a.epoch,1,1,5)
   report['role']=a.role;(a.output/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report));raise SystemExit(0 if report['passed'] else 2)
  import numpy as np
  import row_model
  from integer_peaks import prepare
  from row_results import decode_record,Center,RowDone
  from fractions import Fraction
  def selected(records):
   chosen=[]
   for r in sorted((r for r in records if r['reason']==0),key=lambda r:-r['peak32']):
    if all(abs(r['num']*q['den']-q['num']*r['den'])>=8*r['den']*q['den'] and (r['hi']<q['lo'] or r['lo']>q['hi']) for q in chosen):chosen.append(r)
    if len(chosen)==2:break
   return sorted(chosen,key=lambda r:Fraction(r['num'],r['den']))
  frames=[];ids=[]
  for directory,role in [(a.off_dir,0),(a.on_dir,a.role)]:
   report=json.loads((directory/'report.json').read_text())
   if not report['passed'] or report['role']!=role:raise DiagnosticError('Wrong/unqualified input capture')
   ident=BackgroundIdentity(**report['background']);ids.append(ident)
   current=RoleClient(mmio.read,mmio.write,role=role).snapshot()
   if not current.active or current.background!=ident:raise DiagnosticError('Committed frame changed before processing')
   w,h,data=parse_ppm((directory/'same-frame.ppm').read_bytes());frames.append(np.frombuffer(data,dtype=np.uint8).reshape(h,w,3))
  off,on=frames
  if off.shape!=on.shape:raise DiagnosticError('Geometry changed')
  # Diagnostic subset spans 32 raw columns / two real tiles, full raw height.
  diff=np.maximum(on.astype(np.int16)-off.astype(np.int16),0).max(2);scores=(diff>=80).sum(0);scores[:16]=0;scores[-16:]=0
  peak=int(scores.argmax());x0=max(4,min(w-32,(peak-16)//4*4)) if a.roi_x0 is None else a.roi_x0;x1=x0+32
  if not 0<=x0<=w-32 or x0%4:raise DiagnosticError('Diagnostic ROI must be aligned and inside the image')
  started=time.monotonic()
  summary,payload=JobClient(mmio.read,mmio.write).run(role=a.role,epoch=a.epoch,geometry=1,calibration=1,token=(int(time.time())&0x7fffffff)or 1,width=w,height=h,roi=[x0,0,x1,h],left=4,right=h-5,expected_bg=ids[0],expected_on=ids[1])
  elapsed=time.monotonic()-started;expected={}
  for x in range(x0,x1):
   sig,mx,smooth,base,peaks,_=prepare(on[::-1,x,:],off[::-1,x,:],4,h-5)
   expected[x]=selected(row_model.evaluate(sig,mx,smooth,base,peaks,4,h-5))
  row=x0;centers=0;index=0
  for at in range(0,len(payload),16):
   rec=decode_record(payload[at:at+16])
   if rec.row!=row:raise DiagnosticError('Row sequence mismatch')
   if isinstance(rec,Center):
    if rec.index!=index or index>=len(expected[row]):raise DiagnosticError('Unexpected center')
    g=expected[row][index]
    if (rec.num,rec.den,rec.peak32,rec.lo,rec.hi)!=tuple(g[k] for k in ['num','den','peak32','lo','hi']):raise DiagnosticError('Hardware/software center mismatch')
    index+=1;centers+=1
   else:
    if not isinstance(rec,RowDone) or rec.error or rec.count!=len(expected[row]) or index!=rec.count:raise DiagnosticError('RowDone mismatch')
    row+=1;index=0
  if row!=x1 or centers!=summary['centers']:raise DiagnosticError('Frame completion mismatch')
  a.output.mkdir(parents=True,exist_ok=False);(a.output/'records.bin').write_bytes(payload)
  summary.update(passed=True,roi=[x0,0,x1,h],exact_center_match=True,wall_seconds_including_slow_mailbox=elapsed,hardware_seconds=summary['cycles']/1e8,has_nonzero_centers=centers>0,role=a.role)
  (a.output/'report.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))
if __name__=='__main__':main()

