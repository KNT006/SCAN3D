"""Independent pixel oracle for ABI6. Used only when reference validation is requested."""
import cv2,numpy as np
from scipy.signal import find_peaks,peak_prominences
from spatial_reference import suppress,evaluate,core,spatial_lut,certainly_outside
from rgb_adaptive_strategy import SETTINGS,validate_profile
from row_results import require,Center,RowDone,CandidateExtra

def reference_row(on,off,left,right,known,rad):
 sig=np.maximum(on.astype(np.int16)-off.astype(np.int16),0).max(1).astype(np.uint16);mx=on.max(1)
 pad=np.pad(sig,(2,2),mode='reflect');sm=sum(w*pad[i:i+len(sig)] for i,w in enumerate((1,4,6,4,1)));base=int(np.median(sm[left:right+1])*2);v=sm[left:right+1]
 peaks=np.array([k for k in find_peaks(v)[0] if not certainly_outside(known,rad,k+left,10,70)],int)
 peaks=suppress(peaks,v,8);prom=peak_prominences(v,peaks)[0] if len(peaks) else np.array([]);peaks=peaks[prom>=288]+left
 records=[]
 for r in evaluate(sig,sm,base,peaks,left,right,SETTINGS):
  signal=int(sig[max(0,r['k']-3):r['k']+4].max())
  if r['reason'] or signal<25:continue
  core(r,sm,base,SETTINGS)
  if r['reason']:continue
  xs=np.arange(r['core_lo'],r['core_hi']+1);weights=np.maximum(10*(sm[xs].astype(np.int64)*2-base)-7*r['peak32'],0)
  num=int((weights*xs).sum());den=int(weights.sum());tag=32768+(256 if mx[r['lo']:r['hi']+1].max()>=250 else 0)+signal
  records.append((num,den,tag,r['lo'],r['hi'],r['k'],r['peak32']))
 require(len(records)<=16,'Reference exceeds FPGA candidate capacity; whole frame must be rejected')
 return records

def records_for_images(on,off,header,adapter):
 validate_profile(header);x0,y0,x1,y1=header['geometry']['roi_xyxy'];known,rad=spatial_lut(adapter,[x0,y0,x1,y1],header['laser_id'],70)
 for y in range(y0,y1):
  row=reference_row(on[y],off[y],x0,x1-1,known[y-y0],rad[y-y0])
  for i,(num,den,tag,lo,hi,k,strength) in enumerate(row):
   yield Center(y,i,num,den,tag,lo,hi);yield CandidateExtra(y,i,k,strength)
  yield RowDone(y,len(row))

def software_check_new(off_file,on_file,frame,adapter):
 images=[]
 for f in (off_file,on_file):
  im=cv2.imread(str(f));require(im is not None,'Missing comparison image');images.append(cv2.rotate(im,cv2.ROTATE_90_CLOCKWISE))
 expected=[r for r in records_for_images(images[1],images[0],frame.header,adapter) if isinstance(r,(Center,CandidateExtra))]
 actual=[]
 for c in frame.centers:actual.extend([Center(c.row,c.index,c.num,c.den,c.peak32,c.lo,c.hi),CandidateExtra(c.row,c.index,c.peak_x,c.strength)])
 require(len(actual)==len(expected),'FPGA spatial candidate count mismatch')
 for e,a in zip(expected,actual):require(e==a,'FPGA spatial candidate mismatch: '+repr((e,a)))
 return dict(passed=True,rows=len(frame.rows),centers=len(frame.centers),exact_rational_and_metadata=True,mismatch_rows=0)
