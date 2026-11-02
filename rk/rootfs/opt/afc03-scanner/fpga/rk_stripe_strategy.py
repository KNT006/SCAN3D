"""RK deployment of the verified shared stripe policy; no hardware access here."""
from pathlib import Path
import json,time
import numpy as np
import cv2
from offline_shared_extractor import extract,SETTINGS as STRIPE_SETTINGS
from multipeak_policy import select_centers,SETTINGS as MULTIPEAK_SETTINGS
from ground_branch_policy import select_cloud
VERSION='rk-shared-weak65-ground-branch-v2'
class Frame:
 def __init__(self,header,uv):self.header=header;self.uv=uv
 def processing_uv(self):return self.uv

def process(off_file,on_file,header,adapter,output=None):
 started=time.perf_counter();images=[]
 for file in (off_file,on_file):
  bgr=cv2.imread(str(file));assert bgr is not None and bgr.shape==(1080,1920,3)
  images.append(cv2.rotate(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB),cv2.ROTATE_90_CLOCKWISE))
 records=extract(images[1],images[0],header['geometry']['roi_xyxy'])
 uv=np.asarray([[r['x'],r['y']] for r in records],float).reshape(-1,2);sig=np.asarray([r['signalmax'] for r in records],float)
 new_header=dict(header,algorithm=VERSION,protocol='afc03.rk-stripes.v1')
 # Preserve legacy anchors; add calibrated unique branches through the shared policy.
 ground=adapter.turntable_filter;adapter.turntable_filter=None
 try:cloud=adapter.reconstruct(Frame(new_header,uv))
 finally:adapter.turntable_filter=ground
 selection=select_cloud(uv,sig,cloud,ground)
 arrays=selection['arrays'];ids=selection['indices'];valid=selection['valid']
 selected=selection['selected'];ground_report=selection['ground_report']
 arrays['signal']=sig[ids];arrays['width']=np.asarray([r['width'] for r in records],int)[ids]
 arrays['saturated']=np.asarray([r['saturated'] for r in records],np.uint8)[ids]
 report=dict(version=VERSION,execution='RK3576 CPU',stripe_settings=STRIPE_SETTINGS,multipeak_settings=MULTIPEAK_SETTINGS,
  candidates=len(uv),geometry_valid=int(valid.sum()),base_single_points=len(selected['base_indices']),
  recovered_multi_before_ground=len(selected['recovered_indices']),recovered_multi_after_ground=int(arrays['scheme2'].sum()),
  spatial_filter=selection['spatial_report'],ground_branch=selection['branch_report'],retained_points=len(ids),turntable_filter=ground_report,seconds=time.perf_counter()-started,source_frame_id=header['source_frame_id'],
  inferred_points=0,raw_images_preserved=True,fpga_old_centers_used_as_filter=False)
 if output:
  output=Path(output);np.savez_compressed(output/'strategy-candidates.npz',uv=uv,signal=sig,width=np.asarray([r['width'] for r in records]),geometry_valid=valid)
  (output/'strategy.json').write_text(json.dumps(report,indent=2));(output/'strategy-decisions.json').write_text(json.dumps(selected['decisions'],indent=2))
  (output/'ground-branch-decisions.json').write_text(json.dumps(selection['branch_decisions'],indent=2))
 return arrays,report,new_header
