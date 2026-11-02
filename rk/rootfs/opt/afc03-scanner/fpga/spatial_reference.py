"""Frozen PC oracle helpers; verification only, never production extraction."""
import cv2,numpy as np

def suppress(peaks,v,distance):
 alive=np.ones(len(peaks),bool)
 for j in sorted(range(len(peaks)),key=lambda i:(int(v[peaks[i]]),int(peaks[i])),reverse=True):
  if alive[j]:
   for k in range(j-1,-1,-1):
    if peaks[j]-peaks[k]>=distance:break
    alive[k]=False
   for k in range(j+1,len(peaks)):
    if peaks[k]-peaks[j]>=distance:break
    alive[k]=False
 return peaks[alive]

def evaluate(sig,sm,base,peaks,left,right,p):
 s=sm.astype(np.int64)*2;out=[]
 for i,k in enumerate(peaks):
  k=int(k);pk=int(s[k])-base;r=dict(k=k,x=float(k),peak32=pk,lo=k,hi=k,reason=0)
  if pk<p['prominence']*32:r['reason']=1;out.append(r);continue
  lower,upper=left,right;unresolved=False
  for ni in (i-1,i+1):
   if not 0<=ni<len(peaks):continue
   n=int(peaks[ni]);a,b=sorted([k,n]);valley=a+int(np.argmin(s[a:b+1]));weaker=min(pk,int(s[n])-base)
   if 5*(int(s[valley])-base)>4*weaker:unresolved=True;break
   if n<k:lower=valley+1
   else:upper=valley-1
  if unresolved or lower>k or upper<k:r['reason']=2;out.append(r);continue
  lo=hi=k
  def above(j):return int(s[j])-base>192 and 5*(int(s[j])-base)>pk
  while lo>lower and above(lo-1):lo-=1
  while hi<upper and above(hi+1):hi+=1
  r.update(lo=lo,hi=hi)
  if lo==left or hi==right or not 2<=hi-lo+1<=p['width_max']:r['reason']=3
  out.append(r)
 return out

def core(r,sm,base,p):
 k=r['k'];s=sm.astype(np.int64)*2-base;pk=r['peak32'];lo=hi=k
 while lo>max(r['lo'],k-p['core_radius']) and s[lo-1]>=p['core_fraction']*pk:lo-=1
 while hi<min(r['hi'],k+p['core_radius']) and s[hi+1]>=p['core_fraction']*pk:hi+=1
 w=np.maximum(s[lo:hi+1]*10-(p['core_fraction']*10)*pk,0)
 if not w.sum():r['reason']=6;return
 r.update(x=float(np.sum(w*np.arange(lo,hi+1))/w.sum()),core_lo=lo,core_hi=hi)

def spatial_lut(adapter,roi,label,radius):
 left,top,right,bottom=roi;y,x=np.mgrid[top:bottom,0:1080];uv=np.c_[x.ravel(),y.ravel()].astype(float)
 rays=np.c_[cv2.undistortPoints(uv[:,None],np.array(adapter.camera['camera_matrix']),np.array(adapter.camera['distortion_coefficients'])).reshape(-1,2),np.ones(len(uv))]
 plane=adapter.planes['laser_'+label];den=rays@np.array(plane['normal_camera']);safe=den>.05
 xyz=np.full_like(rays,np.nan);xyz[safe]=rays[safe]*(plane['offset_mm_n_dot_X_equals_offset']/den[safe])[:,None]
 direction=np.array(adapter.axis['axis_direction_for_positive_pulses_camera']);direction/=np.linalg.norm(direction)
 delta=xyz-np.array(adapter.axis['axis_point_closest_to_camera_origin_mm']);rad=np.linalg.norm(delta-(delta@direction)[:,None]*direction,axis=1)
 known=safe&np.isfinite(xyz).all(1)&(xyz[:,2]>80)&(xyz[:,2]<350)
 return known.reshape(x.shape),rad.reshape(x.shape)

def certainly_outside(known,rad,k,core_radius,radius):
 # Include a pixel guard around the possible core center. Unknowns stay candidates.
 lo=max(0,k-core_radius-1);hi=min(len(rad),k+core_radius+2)
 return bool(known[lo:hi].all() and (rad[lo:hi]>radius).all())

