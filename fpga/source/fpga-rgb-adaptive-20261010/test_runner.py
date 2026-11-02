from pathlib import Path
import sys,ast,json,hashlib,numpy as np,cv2
H=Path(__file__).resolve().parent;sys.path[:0]=[str(H/'host')]
from scan_storage import write_ply,sample_rgb
from pointcloud_adapter import PointCloudAdapter
from dual_identity import geometry_candidates
from full_roi import commit_payload
from rgb_adaptive_strategy import process_frame,ALGORITHM
root=H/'runner-merge-test';root.mkdir(exist_ok=True)
source=H.parent/'pc-adaptive-stripes-20261009/input-latest-new-item'
a=PointCloudAdapter(source/'bundle',geometry_candidates)
expected=[]
for idx in (0,34):
 color=cv2.rotate(cv2.cvtColor(cv2.imread(str(source/f'position-{idx:03d}/COLOR/same-frame.png')),cv2.COLOR_BGR2RGB),cv2.ROTATE_90_CLOCKWISE)
 for laser in 'AB':
  h=json.loads((source/f'position-{idx:03d}'/laser/'frame.json').read_text());c={k:h[k] for k in ('stream_epoch','background_generation','geometry','laser_id','laser_control','calibration')};c['algorithm']=ALGORITHM
  frame=commit_payload(c,h['angle'],h['request_id'],h['source_frame_id'],(H/'replay'/f'{idx:03d}-{laser}.bin').read_bytes())
  arrays,_,_=process_frame(frame,a,color=color);arrays['rgb']=sample_rgb(color,arrays['uv']);p=root/f'position-{idx:03d}'/laser;p.mkdir(parents=True,exist_ok=True);np.savez_compressed(p/'points.npz',**arrays)
  expected.append((laser,idx,arrays))
module=ast.parse((H/'scan3d/runner.py').read_text());fn=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='merge');ns=dict(np=np,write_ply=write_ply)
exec(compile(ast.Module(body=[fn],type_ignores=[]),'<runner.merge>','exec'),ns)
summary=ns['merge'](root,[0,34]);expected.sort(key=lambda e:(e[0],e[1]));total=sum(len(e[2]['uv']) for e in expected)
with np.load(root/'combined.npz') as f:
 assert len(f['xyz'])==total
 for k in ('adaptive_origin','threshold'):assert np.array_equal(f[k],np.concatenate([e[2][k] for e in expected]))
 assert f['adaptive_origin'].sum()>0 and not f['inferred'].any()
r=dict(passed=True,points=total,summary=summary,provenance_preserved=True,sha256={str(H/'scan3d/runner.py'):hashlib.sha256((H/'scan3d/runner.py').read_bytes()).hexdigest()})
(H/'runner-validation.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))

