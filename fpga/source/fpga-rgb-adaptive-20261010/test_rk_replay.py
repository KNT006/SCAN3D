from pathlib import Path
import sys,json,time
import cv2,numpy as np
H=Path('/opt/afc03-scanner/candidates/rgb-adaptive-20261010');sys.path[:0]=[str(H/'fpga'),'/opt/afc03-scanner/vendor']
from full_roi import commit_payload
from row_results import ADAPTIVE_ALGORITHM
from rgb_adaptive_strategy import process_frame
from pointcloud_adapter import PointCloudAdapter
from dual_identity import geometry_candidates
adapter=PointCloudAdapter(H/'replay/bundle',geometry_candidates);cv2.setNumThreads(1);rows=[]
for index in (0,34,59):
 color=cv2.rotate(cv2.cvtColor(cv2.imread(str(H/f'replay/{index:03d}-COLOR.png')),cv2.COLOR_BGR2RGB),cv2.ROTATE_90_CLOCKWISE)
 for label in 'AB':
  case=f'{index:03d}-{label}';header=json.loads((H/f'replay/{case}.json').read_text());header['algorithm']=ADAPTIVE_ALGORITHM;context={k:v for k,v in header.items() if k in ('stream_epoch','background_generation','geometry','laser_id','laser_control','calibration','algorithm')}
  started=time.perf_counter();frame=commit_payload(context,header['angle'],header['request_id'],header['source_frame_id'],(H/f'replay/{case}.bin').read_bytes());arrays,report,_=process_frame(frame,adapter,color=color)
  with np.load(H/f'replay/{case}.expected.npz') as expected:
   assert arrays['uv'].shape==expected['uv'].shape and np.allclose(arrays['uv'],expected['uv'],rtol=0,atol=1e-7),case
   assert np.allclose(arrays['axis_frame_mm'],expected['xyz'],rtol=0,atol=1e-6),case
  rows.append(dict(case=case,points=len(arrays['uv']),added=report['adaptive_added'],strategy_seconds=report['seconds'],decode_and_strategy_seconds=time.perf_counter()-started))
result=dict(passed=True,runtime='RK3576 native Python/numpy; isolated candidate; no hardware controls',cases=rows)
(H/'rk-replay-validation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
