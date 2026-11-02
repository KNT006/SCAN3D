"""Integer row evaluator with scipy prominence/distance and final selection.

smooth16 is exactly the 5-tap Gaussian numerator: [1,4,6,4,1].
base32 is twice the median numerator (the median can be half-integral).
"""
import numpy as np
from scipy.signal import find_peaks

def crop_row(on,off,left,right,halo=4):
    """Inclusive ROI plus halo; return global x origin for calibration mapping.

    Two pixels are needed by the Gaussian and three by the signal gate.
    A four-pixel halo preserves both, including edge-adjacent peak tests.
    """
    if halo<4 or not 0<=left<right<len(on) or on.shape!=off.shape:
        raise ValueError('Invalid ROI or insufficient processing halo')
    origin=max(0,left-halo);end=min(len(on),right+halo+1)
    return on[origin:end],off[origin:end],left-origin,right-origin,origin

def prepare(on,off,left,right):
    signal=np.maximum(on.astype(np.int16)-off.astype(np.int16),0).max(1).astype(np.uint16)
    rawmax=on.max(1).astype(np.uint16)
    pad=np.pad(signal,(2,2),mode='reflect')
    smooth=sum(int(w)*pad[j:j+len(signal)] for j,w in enumerate([1,4,6,4,1]))
    base32=int(np.median(smooth[left:right+1])*2)
    peaks,_=find_peaks(smooth[left:right+1].astype(float)/16,distance=8,prominence=18)
    return signal,rawmax,smooth,base32,(peaks+left).astype(int)

def evaluate(signal,rawmax,smooth,base32,peaks,left,right,*,width_max=35,signal_min=80,reject_saturation=True):
    s=smooth.astype(np.int64)*2
    result=[]
    for index,k in enumerate(peaks):
        k=int(k);peak=int(s[k])-base32
        rec=dict(k=k,peak32=peak,reason=0,num=0,den=0,lo=k,hi=k)
        if peak<576:
            rec['reason']=1;result.append(rec);continue
        lower,upper=left,right;unresolved=False
        for ni in [index-1,index+1]:
            if ni<0 or ni>=len(peaks):continue
            neighbor=int(peaks[ni]);a,b=sorted([k,neighbor])
            valley=a+int(np.argmin(s[a:b+1]))
            weaker=min(peak,int(s[neighbor])-base32)
            if 5*(int(s[valley])-base32)>4*weaker:
                unresolved=True;break
            if neighbor<k:lower=valley+1
            else:upper=valley-1
        if unresolved or lower>k or upper<k:
            rec['reason']=2;result.append(rec);continue
        lo=hi=k
        def above(i):return int(s[i])-base32>192 and 5*(int(s[i])-base32)>peak
        while lo>lower and above(lo-1):lo-=1
        while hi<upper and above(hi+1):hi+=1
        rec.update(lo=lo,hi=hi)
        if lo==left or hi==right or not 2<=hi-lo+1<=width_max:
            rec['reason']=3
        elif reject_saturation and rawmax[lo:hi+1].max()>=250:
            rec['reason']=4
        elif signal[max(0,k-3):k+4].max()<signal_min:
            rec['reason']=5
        else:
            weights=np.maximum(2*(s[lo:hi+1]-base32)-peak,0)
            rec['num']=int(np.sum(weights*np.arange(lo,hi+1)))
            rec['den']=int(weights.sum())
            if not rec['den']:rec['reason']=6
        result.append(rec)
    return result

def finalize(records):
    chosen=[]
    for rec in sorted((r for r in records if r['reason']==0),key=lambda r:-r['peak32']):
        x=rec['num']/rec['den']
        if all(abs(x-q['num']/q['den'])>=8 and (rec['hi']<q['lo'] or rec['lo']>q['hi']) for q in chosen):
            chosen.append(rec)
        if len(chosen)==2:break
    return sorted(r['num']/r['den'] for r in chosen)

def extract(on,off,mask):
    selected={};candidates=[];rejected=dict(saturated=0,width_or_border=0,weak=0)
    for y in np.flatnonzero(mask.any(1)):
        xs=np.flatnonzero(mask[y]);left,right=int(xs[0]),int(xs[-1])
        sig,mx,sm,base,peaks=prepare(on[y],off[y],left,right)
        records=evaluate(sig,mx,sm,base,peaks,left,right)
        for r in records:
            if r['reason'] in [3,4,5]:rejected[{3:'width_or_border',4:'saturated',5:'weak'}[r['reason']]]+=1
        points=finalize(records);selected[int(y)]=points
        candidates.extend([[x,int(y)] for x in points])
    return selected,candidates,rejected
