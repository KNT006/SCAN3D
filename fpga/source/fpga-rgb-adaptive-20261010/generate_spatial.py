from pathlib import Path
import sys,json,hashlib
import numpy as np
H=Path(__file__).resolve().parent;P=H.parent/'pc-adaptive-stripes-20261009';sys.path.insert(0,str(P))
import adaptive
D=P/'input-latest-new-item/bundle';a=adaptive.PointCloudAdapter(D,adaptive.geometry_candidates)
words=[0]*4096;maximum=0;pixels=0
for role,laser in enumerate(('A','B')):
 for start in range(0,1920,64):
  known,rad=adaptive.spatial_lut(a,[0,start,1080,min(start+64,1920)],laser,70)
  for i in range(len(known)):
   outside=known[i]&(rad[i]>70)
   # Exact +/-11 neighborhood, clipped at image edges as in PC reference.
   bad=np.r_[0,np.cumsum(~outside)]
   x=np.arange(1080);mask=(bad[np.minimum(x+12,1080)]-bad[np.maximum(x-11,0)])==0
   edges=np.diff(np.r_[False,mask,False].astype(int));ranges=list(zip(np.flatnonzero(edges==1),np.flatnonzero(edges==-1)-1))
   maximum=max(maximum,len(ranges));assert len(ranges)<=2,ranges
   padded=ranges+[(4095,0)]*(2-len(ranges));word=0
   for j,(lo,hi) in enumerate(padded):word|=int(lo)<<(j*24);word|=int(hi)<<(j*24+12)
   words[role*2048+start+i]=word;pixels+=int(mask.sum())
   restored=np.zeros(1080,bool)
   for lo,hi in padded:restored|=(x>=lo)&(x<=hi)
   assert np.array_equal(restored,mask)
   for k in (0,11,140,409,874,1068,1079):assert bool(mask[k])==adaptive.certainly_outside(known[i],rad[i],k,10,70)
path=H/'rtl/spatial_mask.hex';path.write_text(''.join(f'{w:012x}\n' for w in words))
profile=dict(radius_mm=70,core_guard=11,max_intervals=maximum,masked_pixels=pixels,sha256={n:hashlib.sha256((D/(n+'.json')).read_bytes()).hexdigest() for n in ('axis','camera','planes')},rom_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
(H/'spatial-profile.json').write_text(json.dumps(profile,indent=2));print(json.dumps(profile))
