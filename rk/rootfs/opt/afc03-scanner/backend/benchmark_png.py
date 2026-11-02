"""Lossless PNG encoder comparison on saved frames; no hardware calls."""
import cv2,json,time,os,sys
from pathlib import Path
import numpy as np
from timing import statistics
root=Path(sys.argv[1]);source=Path(sys.argv[2]);rows=[]
files=[root/'first.png']+[source/f'position{i:03d}_laser_on.png' for i in [0,60,120]]+[source/'color'/f'position{i:03d}_color.png' for i in [0,60,120]]
variants={'current':[], 'level1_rle':[cv2.IMWRITE_PNG_COMPRESSION,1,cv2.IMWRITE_PNG_STRATEGY,cv2.IMWRITE_PNG_STRATEGY_RLE], 'level1_default':[cv2.IMWRITE_PNG_COMPRESSION,1], 'level0':[cv2.IMWRITE_PNG_COMPRESSION,0]}
for index,f in enumerate(files):
 im=cv2.imread(str(f));assert im is not None
 entries=list(variants.items())
 entries=entries[index%4:]+entries[:index%4]
 for name,flags in entries:
  t=time.monotonic();ok,b=cv2.imencode('.png',im,flags);elapsed=(time.monotonic()-t)*1000;assert ok
  assert np.array_equal(cv2.imdecode(b,cv2.IMREAD_COLOR),im)
  target=root/'png-probe.bin';t=time.monotonic()
  with target.open('wb') as h:h.write(b)
  write_ms=(time.monotonic()-t)*1000;t=time.monotonic()
  with target.open('rb') as h:os.fsync(h.fileno())
  sync_ms=(time.monotonic()-t)*1000
  rows.append(dict(file=str(f),variant=name,encode_ms=elapsed,write_ms=write_ms,fsync_ms=sync_ms,bytes=len(b),pixel_exact=True))
 print('png sample',index+1,flush=True)
result=dict(rows=rows,summary={name:{key:statistics([r[key] for r in rows if r['variant']==name]) for key in ['encode_ms','write_ms','fsync_ms','bytes']} for name in variants},all_pixel_exact=True,limits='Seven saved samples; timing under existing 250% CPU budget, preview and HDMI browser active')
(root/'png_report.json').write_text(json.dumps(result,indent=2));print(json.dumps(result['summary']))
