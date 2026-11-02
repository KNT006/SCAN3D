"""Consume tagged FPGA candidates without reading/re-extracting raw images.

Continuity runs on sparse records, before and after weak-width gating.
Geometry-valid single-row anchors are preserved.
"""
from pathlib import Path
import json,time
import numpy as np
from offline_shared_extractor import continuity,SETTINGS as STRIPE_SETTINGS
from multipeak_policy import select_centers,SETTINGS as MULTIPEAK_SETTINGS
from ground_branch_policy import select_cloud
from rk_stripe_strategy import Frame
from row_results import require
VERSION='fpga-brightcore-rk-ground-branch-v2'
ALGORITHM='fpga-brightcore-width100-signal40-v1'

def candidate_records(frame):
 require(frame.header['algorithm']==ALGORITHM,'Wrong FPGA extraction algorithm')
 records=[]
 for c in frame.centers:
  require(c.peak32 & 0xfe00 == 0x8000,'Wrong FPGA metadata tag')
  records.append(dict(x=c.num/c.den+frame.header['geometry']['global_x_origin'],y=c.row,
      width=c.hi-c.lo+1,signalmax=c.peak32 & 255,saturated=(c.peak32>>8)&1))
 return records

def process_frame(frame,adapter,output=None):
 started=time.perf_counter();header=frame.header
 raw=candidate_records(frame)
 first=continuity(raw)
 records=continuity([r for r in first if r['signalmax']>=80 or r['width']<=65])
 uv=np.asarray([[r['x'],r['y']] for r in records],float).reshape(-1,2)
 sig=np.asarray([r['signalmax'] for r in records],float)
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
 report=dict(version=VERSION,execution='FPGA pixel and row extraction; RK sparse continuity/geometry/scheme2/ground-branch',stripe_settings=STRIPE_SETTINGS,multipeak_settings=MULTIPEAK_SETTINGS,
  candidates=len(uv),geometry_valid=int(valid.sum()),base_single_points=len(selected['base_indices']),
  recovered_multi_before_ground=len(selected['recovered_indices']),recovered_multi_after_ground=int(arrays['scheme2'].sum()),
  spatial_filter=selection['spatial_report'],ground_branch=selection['branch_report'],retained_points=len(ids),turntable_filter=ground_report,seconds=time.perf_counter()-started,source_frame_id=header['source_frame_id'],
  inferred_points=0,raw_images_preserved=True,fpga_old_centers_used_as_filter=False,raw_images_read_for_extraction=False)
 if output:
  output=Path(output);np.savez_compressed(output/'strategy-candidates.npz',uv=uv,signal=sig,width=np.asarray([r['width'] for r in records]),geometry_valid=valid)
  (output/'strategy.json').write_text(json.dumps(report,indent=2));(output/'strategy-decisions.json').write_text(json.dumps(selected['decisions'],indent=2))
  (output/'ground-branch-decisions.json').write_text(json.dumps(selection['branch_decisions'],indent=2))
 return arrays,report,new_header
