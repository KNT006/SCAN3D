import argparse,json,time
from pathlib import Path
import cv2,numpy as np
from manual_peaks import extract
from row_results import decode_record,Center
p=argparse.ArgumentParser();p.add_argument('session',type=Path);a=p.parse_args();cv2.setNumThreads(2)
cfg=json.loads((Path(__file__).parent/'bundle/config.json').read_text());x0,y0,x1,y1=cfg['scan_roi']
mask=np.zeros((1920,1080),np.uint8);mask[y0:y1,x0:x1]=255
def image(name):return cv2.rotate(cv2.imread(str(a.session/name/'same-frame.ppm')),cv2.ROTATE_90_CLOCKWISE)
off=image('OFF');report={}
for label in ('A','B'):
    on=image(label);durations=[]
    for i in range(4):
        t=time.perf_counter();chosen,points,rejected=extract(on,off,mask);elapsed=time.perf_counter()-t
        if i:durations.append(elapsed)
    data=(a.session/label/'records.bin').read_bytes();hardware={}
    for i in range(0,len(data),16):
        r=decode_record(data[i:i+16])
        if isinstance(r,Center):hardware.setdefault(r.row,[]).append(r.num/r.den)
    mismatches=[];errors=[]
    for row in range(y0,y1):
        aa=hardware.get(row,[]);bb=chosen.get(row,[])
        if len(aa)!=len(bb):mismatches.append(row)
        else:errors.extend(abs(x-y) for x,y in zip(aa,bb))
    report[label]=dict(rk_seconds=durations,rk_median_s=float(np.median(durations)),
        centers=len(points),rejected=rejected,count_mismatch_rows=mismatches,
        max_center_difference_px=max(errors,default=0),
        on_max=int(on.max()),on_roi_saturated_pixels=int((on[y0:y1,x0:x1].max(2)>=250).sum()))
(a.session/'existing-rk-benchmark.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
