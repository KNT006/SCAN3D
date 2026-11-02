"""Features from archived candidates only; never fabricates missing intensity profiles."""
from pathlib import Path
import json,time
import numpy as np
H=Path(__file__).resolve().parent; O=H/'output'

def features(records):
 rows={}
 for r in records:
  if r['new_kept']:rows.setdefault(r['y'],[]).append(r)
 anchors={y:max(rs,key=lambda r:r['signalmax']) for y,rs in rows.items()}
 result={}
 for y,rs in rows.items():
  if len(rs)<2:continue
  a=anchors[y]
  supports=[(yy,b) for yy,b in anchors.items() if 0<abs(yy-y)<=4 and b['signalmax']>=80 and abs(b['x']-a['x'])<=2+2*abs(yy-y)]
  if len(supports)>=3:
   fit=np.polyfit([yy-y for yy,b in supports],[b['x'] for yy,b in supports],1)
   pred=float(fit[1]);res=float(np.median([abs(b['x']-np.polyval(fit,yy-y)) for yy,b in supports]))
  else:pred=a['x'];res=999.
  for r in rs:
   if r is a:continue
   result[r['_id']]=dict(primary_x=a['x'],primary_signal=a['signalmax'],ratio=r['signalmax']/max(a['signalmax'],1),gap=abs(r['x']-a['x']),anchor_rows=len(supports),trajectory_error=abs(r['x']-pred),primary_error=abs(a['x']-pred),fit_residual=res)
 return result

def preliminary(r,f,width=28,ratio=.5):
 return (r['signalmax']<80 and r['width']>=width and f['primary_signal']>=100 and f['ratio']<=ratio and 16<=f['gap']<=90 and f['anchor_rows']>=5 and f['fit_residual']<=2 and f['primary_error']<=3 and f['trajectory_error']>=14)

def decisions(records,width=28,ratio=.5):
 fs=features(records);suspects=[r for r in records if r['_id'] in fs and preliminary(r,fs[r['_id']],width,ratio)]
 by={}
 for r in suspects:by.setdefault(r['y'],[]).append(r)
 rejected=set()
 for r in suspects:
  n=sum(any(abs(q['x']-r['x'])<=2+3*abs(dy) for q in by.get(r['y']+dy,[])) for dy in range(-4,5) if dy)
  fs[r['_id']]['weak_branch_rows']=n
  if n>=3:rejected.add(r['_id'])
 return rejected,fs

