"""Independent saved-pixel oracle. Validation only, never production extraction."""
from pathlib import Path
import numpy as np
import cv2
from offline_shared_extractor import fast_prepare,evaluate,choose
from row_results import require

def reference_row(on,off,left,right):
 sig,mx,sm,base,peaks=fast_prepare(on,off,left,right)
 records=evaluate(sig,mx,sm,base,peaks,left,right)
 for r in records:
  if r['reason']:continue
  k=r['k'];v=sm.astype(np.int64)*2-base;pk=r['peak32'];lo=hi=k
  while lo>max(r['lo'],k-10) and int(v[lo-1])*10>=7*pk:lo-=1
  while hi<min(r['hi'],k+10) and int(v[hi+1])*10>=7*pk:hi+=1
  weights=np.maximum(v[lo:hi+1]*10-7*pk,0)
  r['num']=int(np.sum(weights*np.arange(lo,hi+1)));r['den']=int(weights.sum())
 selected=choose(records)
 for r in selected:
  k=r['k'];r['meta']=0x8000|int(sig[max(0,k-3):k+4].max())|(int(mx[r['lo']:r['hi']+1].max()>=250)<<8)
 return selected

def software_check_new(off_file,on_file,frame):
 images=[]
 for f in (off_file,on_file):
  im=cv2.imread(str(f));require(im is not None,'Missing comparison image')
  images.append(cv2.rotate(im,cv2.ROTATE_90_CLOCKWISE))
 actual={}
 for c in frame.centers:actual.setdefault(c.row,[]).append(c)
 x0,y0,x1,y1=frame.header['geometry']['roi_xyxy']
 mismatches=[]
 for y in range(y0,y1):
  rs=reference_row(images[1][y],images[0][y],x0,x1-1)
  expected=[tuple(r[k] for k in ('num','den','meta','lo','hi')) for r in rs]
  got=[(c.num,c.den,c.peak32,c.lo,c.hi) for c in actual.get(y,[])]
  if got!=expected:mismatches.append(dict(row=y,expected=expected,actual=got))
 require(not mismatches,'FPGA new-strategy mismatch: '+repr(mismatches[:3]))
 return dict(passed=True,rows=y1-y0,centers=len(frame.centers),exact_rational_and_metadata=True,mismatch_rows=0)
