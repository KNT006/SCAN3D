import cv2,time,json,numpy as np,os
from pathlib import Path
r=Path('/opt/afc03-scanner/diagnostics/capture-20260928');src=Path('/opt/afc03-scanner/jobs/live-6747890550074451a8c4ccc8f0e3c18e');rows=[]
for source in [r/'first.png',src/'position000_laser_on.png',src/'color/position000_color.png']:
 im=cv2.imread(str(source))
 for order in range(3):
  for mode in (['direct','buffered'] if order%2==0 else ['buffered','direct']):
   p=r/('save-'+mode+'.png');start=time.monotonic()
   if mode=='direct':assert cv2.imwrite(str(p),im)
   else:
    ok,b=cv2.imencode('.png',im);assert ok
    with p.open('wb') as f:f.write(b)
   elapsed=(time.monotonic()-start)*1000
   assert np.array_equal(im,cv2.imread(str(p)))
   rows.append(dict(file=str(source),repeat=order,mode=mode,ms=elapsed,bytes=p.stat().st_size))
  print(source.name,order,flush=True)
(r/'png_io_report.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows))
