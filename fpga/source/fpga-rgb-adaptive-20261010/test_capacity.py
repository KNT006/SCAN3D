from pathlib import Path
import sys,json,subprocess,numpy as np
H=Path(__file__).resolve().parent;PC=H.parent/'pc-adaptive-stripes-20261009';sys.path.insert(0,str(PC));import adaptive as a
from scipy.signal import find_peaks,peak_prominences
rom=[int(x,16) for x in (H/'rtl/spatial_mask.hex').read_text().split()]
P=dict(a.DEFAULT,adaptive_min=25,dark_v=100,bright_v=160,noise_gate=False)
cases=[]
for idx in ():
 folder=PC/'input-latest-new-item'/f'position-{idx:03d}';off=a.image(folder/'OFF')
 for b,label in enumerate('AB'):
  on=a.image(folder/label)
  for y in sorted(set([1000,1001,1658,1659,1121,*range(1020,1640,37),*range(1115,1127)])):
   sig=np.maximum(on[y].astype(np.int16)-off[y].astype(np.int16),0).max(1).astype(np.uint16);mx=on[y].max(1)
   cases.append((f'{idx:03d}-{label}-{y}',y,b,140,879,sig,mx))
for n in (0,3,16,17):
 sig=np.zeros(1080,np.uint16)
 for k in range(n):sig[160+k*30:165+k*30]=40+k
 cases.append((f'synthetic-{n}',0,0,1,1078,sig,sig))
manifest=[]
with (H/'capacity-vectors.txt').open('w') as f:
 f.write(str(len(cases))+'\n')
 for name,y,b,left,right,sig,mx in cases:
  sm=sum(w*np.pad(sig,(2,2),mode='reflect')[i:i+len(sig)] for i,w in enumerate((1,4,6,4,1)));base=int(np.median(sm[left:right+1])*2);v=sm[left:right+1]
  peaks=find_peaks(v)[0];ranges=rom[b*2048+y];rr=[(ranges>>(24*i)&4095,ranges>>(24*i+12)&4095) for i in range(2)]
  peaks=np.array([k for k in peaks if not any(lo<=k+left<=hi for lo,hi in rr)],int)
  peaks=a.suppress(peaks,v,8);prom=peak_prominences(v,peaks)[0] if len(peaks) else np.array([]);peaks=peaks[prom>=288]+left
  records=[]
  for r in a.evaluate(sig,sm,base,peaks,left,right,P):
   signal=int(sig[max(0,r['k']-3):r['k']+4].max())
   if r['reason'] or signal<25:continue
   a.core(r,sm,base,P)
   if r['reason']:continue
   xs=np.arange(r['core_lo'],r['core_hi']+1);weights=np.maximum(10*(sm[xs].astype(np.int64)*2-base)-7*r['peak32'],0)
   num=int((weights*xs).sum());den=int(weights.sum());tag=32768+(256 if mx[r['lo']:r['hi']+1].max()>=250 else 0)+signal
   records.append((num,den,tag,r['lo'],r['hi'],r['k']*65536+r['peak32']))
  error=int(len(records)>16);manifest.append(dict(name=name,count=len(records),error=error));records=[] if error else records
  f.write(f'{len(sig)} {y} {b} {left} {right} {len(records)} {error}\n')
  for si,ma in zip(sig,mx):f.write(f'{int(ma)*256+int(si):04x}\n')
  for row in records:f.write(' '.join(map(str,row))+'\n')
(H/'capacity-vector-manifest.json').write_text(json.dumps(manifest,indent=2))
ss=[H/'rtl'/n for n in ('laser_full_row_core.v','laser_peak_frontend.v','laser_row_evaluator_precomputed.v')]+[H/'tb_capacity.sv'];BIN=H.parent/'capture-repair-20260928/tools/bin'
r=subprocess.run([str(BIN/'iverilog.exe'),'-g2012','-s','tb','-o',str(H/'capacity.vvp'),*map(str,ss)],capture_output=True,text=True);assert r.returncode==0,r.stderr
r=subprocess.run([str(BIN/'vvp.exe'),str(H/'capacity.vvp')],cwd=H,capture_output=True,text=True,timeout=300);(H/'capacity-test.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
print(r.stdout[-1000:]);import hashlib
(H/'capacity-validation.json').write_text(json.dumps(dict(passed=True,rows=len(cases),sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in ss}),indent=2))
