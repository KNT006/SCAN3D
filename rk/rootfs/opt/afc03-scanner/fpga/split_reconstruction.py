"""B-only post-selection reconstruction; FPGA and selection retain audited geometry."""
import hashlib,json
from pathlib import Path
import cv2
import numpy as np
from row_results import require,angle_degrees

def load_profile(bundle):
    bundle=Path(bundle);path=bundle/'reconstruction_B.json'
    if not path.exists():return None
    p=json.loads(path.read_text())
    require(p['mode']=='B_post_selection_v1','Unsupported reconstruction mode')
    for name in ('camera','axis','planes'):
        require(hashlib.sha256((bundle/(name+'.json')).read_bytes()).hexdigest()==p['acquisition_hashes'][name+'_sha256'],'Reconstruction acquisition binding mismatch')
    n=np.asarray(p['normal_camera'],float)
    require(n.shape==(3,) and np.isfinite(n).all() and abs(np.linalg.norm(n)-1)<1e-6,'Invalid B normal')
    require(np.isfinite(p['offset_mm']) and p['offset_mm']>0,'Invalid B offset')
    return p

def apply(arrays,header,bundle):
    p=load_profile(bundle)
    if p is None:return arrays,None
    meta=dict(mode=p['mode'],applied=header['laser_id']=='B',acquisition_hashes=p['acquisition_hashes'],profile_sha256=hashlib.sha256((Path(bundle)/'reconstruction_B.json').read_bytes()).hexdigest(),absolute_accuracy_validated=False,selection_geometry='original FPGA/RK calibration; excluded points cannot be recovered')
    if header['laser_id']!='B':return arrays,meta
    xyz=np.asarray(arrays['camera_xyz_mm'],float);normal=np.asarray(p['normal_camera']);den=xyz@normal
    require(np.isfinite(xyz).all() and np.all(den>1e-9),'Invalid B intersection rays')
    new=xyz*(p['offset_mm']/den)[:,None]
    axis=json.loads((Path(bundle)/'axis.json').read_text());direction=np.asarray(axis['axis_direction_for_positive_pulses_camera'],float);direction/=np.linalg.norm(direction)
    require(header['angle']['source']=='commanded_pulses_no_encoder','Unsupported angle source for split reconstruction')
    center=np.asarray(axis['axis_point_closest_to_camera_origin_mm']);rotation=cv2.Rodrigues(direction*np.deg2rad(angle_degrees(header['angle'])))[0]
    aligned=(new-center)@rotation+center;ex=np.array([1.,0.,0.]);ex-=direction*(ex@direction);ex/=np.linalg.norm(ex);basis=np.array([ex,direction,np.cross(ex,direction)])
    result=dict(arrays,camera_xyz_mm=new,camera_aligned_mm=aligned,axis_frame_mm=(aligned-center)@basis.T)
    require(all(np.isfinite(result[k]).all() for k in ('camera_xyz_mm','camera_aligned_mm','axis_frame_mm')),'Non-finite reconstructed B')
    return result,meta
