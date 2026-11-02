"""Shared weak-width strategy, accelerated CPU replay with deterministic peak ties."""
import numpy as np
from scipy.signal import find_peaks,peak_prominences
import row_model
def evaluate(signal,rawmax,smooth,base32,peaks,left,right):
 return row_model.evaluate(signal,rawmax,smooth,base32,peaks,left,right,
                           width_max=100,signal_min=40,reject_saturation=False)

SETTINGS=dict(signal_min=40,weak_signal_below=80,weak_width_max=65,strong_width_max=100,
 saturation_rejection=False,core_peak_fraction=.7,core_radius=10,neighbor_rows=4,min_support=3,
 max_dx='2+3*abs(dy)',interpolate=False,same_for_A_B=True)
def fast_prepare(on,off,left,right):
 sig=np.maximum(on.astype(np.int16)-off.astype(np.int16),0).max(1).astype(np.uint16)
 mx=on.max(1).astype(np.uint16);pad=np.pad(sig,(2,2),mode='reflect')
 sm=sum(w*pad[i:i+len(sig)] for i,w in enumerate((1,4,6,4,1)))
 v=sm[left:right+1];peaks=find_peaks(v)[0]
 alive=np.ones(len(peaks),bool)
 # Distance is resolved BEFORE prominence, same right-first equal-height rule.
 for j in sorted(range(len(peaks)),key=lambda i:(int(v[peaks[i]]),int(peaks[i])),reverse=True):
  if alive[j]:
   for k in range(j-1,-1,-1):
    if peaks[j]-peaks[k]>=8:break
    alive[k]=False
   for k in range(j+1,len(peaks)):
    if peaks[k]-peaks[j]>=8:break
    alive[k]=False
 separated=peaks[alive]
 prom=peak_prominences(v,separated)[0] if len(separated) else np.array([])
 return sig,mx,sm,int(np.median(v)*2),separated[prom>=288]+left
def choose(rs):
 out=[]
 for r in sorted((r for r in rs if r['reason']==0),key=lambda r:-r['peak32']):
  x=r['num']/r['den']
  if all(abs(x-q['num']/q['den'])>=8 and (r['hi']<q['lo'] or r['lo']>q['hi']) for q in out):out.append(r)
  if len(out)==2:break
 return sorted(out,key=lambda r:r['num']/r['den'])
def continuity(points):
 rows={}
 for r in points:rows.setdefault(r['y'],[]).append(r)
 return [r for r in points if sum(any(abs(q['x']-r['x'])<=2+3*abs(dy) for q in rows.get(r['y']+dy,[])) for dy in range(-4,5) if dy)>=3]
def extract(on,off,roi):
 left,top,right,bottom=roi;right-=1;points=[]
 for y in range(top,bottom):
  sig,mx,sm,base,peaks=fast_prepare(on[y],off[y],left,right)
  records=evaluate(sig,mx,sm,base,peaks,left,right)
  for r in records:
   if r['reason']:continue
   k=r['k'];s=sm.astype(np.int64)*2-base;pk=r['peak32'];lo=hi=k
   while lo>max(r['lo'],k-10) and int(s[lo-1])*10>=7*pk:lo-=1
   while hi<min(r['hi'],k+10) and int(s[hi+1])*10>=7*pk:hi+=1
   weights=np.maximum(s[lo:hi+1]*10-7*pk,0)
   r['num']=int(np.sum(weights*np.arange(lo,hi+1)));r['den']=int(weights.sum())
  for r in choose(records):
   k=r['k'];points.append(dict(x=r['num']/r['den'],y=y,k=k,width=r['hi']-r['lo']+1,
      signalmax=int(sig[max(0,k-3):k+4].max()),saturated=int(mx[r['lo']:r['hi']+1].max()>=250)))
 first=continuity(points)
 gated=[r for r in first if r['signalmax']>=80 or r['width']<=65]
 return continuity(gated)
