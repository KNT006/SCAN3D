"""Offline-only worker. No motor, serial, camera control, or network code."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import runpy
import shutil
import sys
import time

import cv2
import numpy as np

def write_json(path, value):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(path)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--dataset',type=Path,required=True);parser.add_argument('--job',type=Path,required=True)
    args=parser.parse_args();source=args.dataset;job=args.job;out=job/'output';out.mkdir(exist_ok=True)
    started=time.perf_counter();state=json.loads((job/'job.json').read_text())
    def update(**values):state.update(values);write_json(job/'job.json',state)
    try:
        update(status='running',stage='extracting',progress=0)
        sys.path.insert(0,str(source));from scan_analysis import rotated,stripe,repeat_error
        bg=rotated(cv2.imread(str(source/'background.png')))
        baseline_diff=[];points=[];extract_started=time.perf_counter()
        for i in range(181):
            label=f'position{i:03d}'
            raw=cv2.imread(str(source/(label+'_laser_on.png')))
            repeat=cv2.imread(str(source/(label+'_laser_on_repeat.png')))
            if raw is None or repeat is None:raise ValueError(f'Missing raw frame {label}')
            uv,widths,rejected=stripe(rotated(raw),bg)
            other,_,_=stripe(rotated(repeat),bg)
            original=np.load(source/(label+'_stripe.npz'))
            same=uv.shape==original['uv'].shape
            delta=float(np.abs(uv-original['uv']).max()) if same and len(uv) else (0. if same else None)
            baseline_diff.append({'index':i,'same_point_shape':same,'max_abs_uv_difference_px':delta})
            np.savez(out/(label+'_stripe.npz'),uv=uv,repeat_uv=other,widths=widths)
            shutil.copy2(source/(label+'_record.json'),out/(label+'_record.json'))
            points.append(len(uv))
            if i%5==0 or i==180:update(progress=round((i+1)/181*75,1),processed_positions=i+1)
        extract_seconds=time.perf_counter()-extract_started
        for name in ['scan_config.json','fine_run_state.json','laser_plane_v2_provisional.json','turntable_axis_v1_provisional.json','reconstruct_fine.py']:
            shutil.copy2(source/name,out/name)
        update(stage='reconstructing',progress=77)
        reconstruction_started=time.perf_counter();runpy.run_path(str(out/'reconstruct_fine.py'),run_name='__main__')
        reconstruction_seconds=time.perf_counter()-reconstruction_started
        update(stage='validating',progress=94)
        old=np.load(source/'fine_cloud_arrays.npz');new=np.load(out/'fine_cloud_arrays.npz')
        oldmesh=np.load(source/'fine_mesh_arrays.npz');newmesh=np.load(out/'fine_mesh_arrays.npz')
        same_cloud_shape=old['camera_aligned_mm'].shape==new['camera_aligned_mm'].shape
        point_error=np.linalg.norm(old['camera_aligned_mm']-new['camera_aligned_mm'],axis=1) if same_cloud_shape else np.array([np.inf])
        mesh_shape=oldmesh['display_vertices_mm'].shape==newmesh['display_vertices_mm'].shape
        mesh_delta=float(np.max(np.abs(oldmesh['display_vertices_mm']-newmesh['display_vertices_mm']))) if mesh_shape else None
        faces_equal=np.array_equal(oldmesh['faces'],newmesh['faces'])
        compatible=all(r['same_point_shape'] and r['max_abs_uv_difference_px'] is not None and r['max_abs_uv_difference_px']<1e-6 for r in baseline_diff)
        passed=compatible and same_cloud_shape and float(point_error.max())<1e-5 and mesh_delta is not None and mesh_delta<1e-5 and faces_equal
        report={'passed':passed,'meaning':'Cross-platform software equivalence on identical recorded inputs, not a physical accuracy certification.',
                'positions':181,'raw_frames':362,'point_count':len(new['camera_aligned_mm']),
                'max_uv_difference_px':max((r['max_abs_uv_difference_px'] or 0) for r in baseline_diff),'stripe_point_shapes_equal':all(r['same_point_shape'] for r in baseline_diff),
                'point_distance_max_mm':float(point_error.max()) if same_cloud_shape else None,
                'point_distance_p95_mm':float(np.percentile(point_error,95)) if same_cloud_shape else None,
                'mesh_coordinate_max_difference_mm':mesh_delta,'mesh_faces_equal':faces_equal,
                'extract_seconds':extract_seconds,'reconstruction_seconds':reconstruction_seconds,'elapsed_seconds':time.perf_counter()-started,
                'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
                'numpy_version':np.__version__,'opencv_version':cv2.__version__,
                'calibration_sha256':{name:hashlib.sha256((source/name).read_bytes()).hexdigest() for name in ['laser_plane_v2_provisional.json','turntable_axis_v1_provisional.json']},
                'tolerances':{'stripe_abs_px':1e-6,'geometry_mm':1e-5},'profiles':baseline_diff}
        write_json(job/'validation.json',report)
        update(status='completed' if passed else 'validation_failed',stage='completed',progress=100,validation={k:v for k,v in report.items() if k!='profiles'})
    except Exception as exc:
        update(status='failed',stage='failed',error=str(exc),elapsed_seconds=time.perf_counter()-started)
        raise

if __name__=='__main__':main()
