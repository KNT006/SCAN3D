from pathlib import Path
import sys,json,hashlib,compileall,time
import numpy as np,cv2
H=Path(__file__).resolve().parent;PC=H.parent/'pc-adaptive-stripes-20261009';sys.path.insert(0,str(H/'host'))
from row_results import ADAPTIVE_ALGORITHM
from compare_spatial_candidates import records_for_images
from full_roi import commit_payload
from rgb_adaptive_strategy import process_frame
from pointcloud_adapter import PointCloudAdapter
from dual_identity import geometry_candidates
assert compileall.compile_dir(str(H/'host'),quiet=1)
source=PC/'input-latest-new-item';adapter=PointCloudAdapter(source/'bundle',geometry_candidates)
def im(p):
 b=cv2.imread(str(p/'same-frame.png'));assert b is not None
 return cv2.rotate(cv2.cvtColor(b,cv2.COLOR_BGR2RGB),cv2.ROTATE_90_CLOCKWISE)
cv2.setNumThreads(1);cases=[];started=time.perf_counter();target=H/'replay';target.mkdir(exist_ok=True)
for index in range(61):
 folder=source/f'position-{index:03d}';off=im(folder/'OFF');color=im(folder/'COLOR')
 for label in 'AB':
  h=json.loads((folder/label/'frame.json').read_text());h['algorithm']=ADAPTIVE_ALGORITHM
  context={k:v for k,v in h.items() if k in ('stream_epoch','background_generation','geometry','laser_id','laser_control','calibration','algorithm')}
  payload=(target/f'{index:03d}-{label}.bin').read_bytes() if '--cached' in sys.argv else b''.join(r.encode() for r in records_for_images(im(folder/label),off,h,adapter))
  frame=commit_payload(context,h['angle'],h['request_id'],h['source_frame_id'],payload)
  arrays,report,_=process_frame(frame,adapter,color=color)
  ref=json.loads((PC/f'output/latest-new-item-rgb100-160/{index:03d}-{label}/data.json').read_text(encoding='utf-8'))['modes']['early_adaptive']['points']
  uv=np.array([[r['x'],r['y']] for r in ref]).reshape(-1,2);xyz=np.array([r['xyz'] for r in ref]).reshape(-1,3)
  assert arrays['uv'].shape==uv.shape,(index,label,arrays['uv'].shape,uv.shape)
  assert np.allclose(arrays['uv'],uv,rtol=0,atol=1e-7),(index,label,'uv')
  assert np.allclose(arrays['axis_frame_mm'],xyz,rtol=0,atol=1e-6),(index,label,'xyz')
  (target/f'{index:03d}-{label}.bin').write_bytes(payload)
  cases.append(dict(index=index,laser=label,candidates=len(frame.centers),points=len(uv),added=report['adaptive_added'],seconds=report['seconds']))
 print(index,sum(r['points'] for r in cases[-2:]),flush=True)
(H/'host-replay-validation.json').write_text(json.dumps(dict(passed=True,cases=cases,points_excluding_closure=sum(r['points'] for r in cases if r['index']<60),seconds=time.perf_counter()-started,sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (H/'host').glob('*.py')}),indent=2))
print('REPLAY_PASS',len(cases))
