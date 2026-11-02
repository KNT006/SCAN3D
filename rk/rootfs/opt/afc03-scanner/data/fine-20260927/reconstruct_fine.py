"""Reconstruct the independent fine scan. Raw points and an explicitly open side mesh are separate outputs."""
import colorsys
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np

p=Path(__file__).resolve().parent
run=json.loads((p/'fine_run_state.json').read_text())
assert run['status']=='completed' and run['completed_positions']==181
cfg=json.loads((p/'scan_config.json').read_text())
laser=json.loads((p/'laser_plane_v2_provisional.json').read_text())
axis=json.loads((p/'turntable_axis_v1_provisional.json').read_text())
K=np.array(laser['camera']['camera_matrix']);dist=np.array(laser['camera']['distortion_coefficients'])
n=np.array(laser['normal_camera']);d=laser['offset_mm_n_dot_X_equals_offset']
a=np.array(axis['axis_direction_for_positive_encoder_camera']);c=np.array(axis['axis_point_closest_to_camera_origin_mm'])
ex=np.array([1.,0,0]);ex-=a*(ex@a);ex/=np.linalg.norm(ex);ez=np.cross(ex,a)
records=[];cloud=[];display_parts=[];angles=[];positions=[];samples=[];all_uv=[];all_rawxyz=[]
for index in range(181):
    label=f'position{index:03d}'
    record=json.loads((p/(label+'_record.json')).read_text())
    assert record['status']=='captured_and_verified'
    uv=np.load(p/(label+'_stripe.npz'))['uv']
    xy=cv2.undistortPoints(uv[:,None,:],K,dist).reshape(-1,2)
    rays=np.column_stack((xy,np.ones(len(xy))))
    denom=rays@n;assert (denom>.05).all()
    xyz=rays*(d/denom)[:,None]
    h=(xyz-c)@a;radius=np.linalg.norm(xyz-c-h[:,None]*a,axis=1)
    valid=(xyz[:,2]>80)&(xyz[:,2]<350)&(radius<90)&np.isfinite(xyz).all(1)
    uv=uv[valid];xyz=xyz[valid]
    angle=record['motion']['after']
    R=cv2.Rodrigues(a*np.deg2rad(angle-cfg['start_encoder_degrees']))[0]
    aligned=(xyz-c)@R+c
    v=aligned-c
    display=np.column_stack((v@ex,v@a,v@ez))
    np.savez(p/(label+'_reconstruction.npz'),uv=uv,camera_xyz_mm=xyz,aligned_xyz_mm=aligned,axis_frame_mm=display,encoder_degrees=angle)
    all_uv.append(uv);all_rawxyz.append(xyz);positions.append(aligned)
    if index<180:
        rgb=np.round(np.array(colorsys.hsv_to_rgb(index/180*.8,.65,.9))*255).astype(int)
        cloud.append(np.column_stack((aligned,np.tile(rgb,(len(uv),1)))))
        display_parts.append(display);angles.extend([angle-cfg['start_encoder_degrees']]*len(uv))
        samples.append(display)
    records.append({'index':index,'angle':angle,'points':len(uv),
                    'geometry_rejected':int((~valid).sum()),'quality':record['quality']})
first_map={int(y):j for j,(_,y) in enumerate(all_uv[0])}
end_index=[j for j,(_,y) in enumerate(all_uv[-1]) if int(y) in first_map]
first_index=[first_map[int(all_uv[-1][j,1])] for j in end_index]
pixel_delta=np.linalg.norm(all_uv[-1][end_index]-all_uv[0][first_index],axis=1)
xyz_delta=np.linalg.norm(all_rawxyz[-1][end_index]-all_rawxyz[0][first_index],axis=1)
aligned_delta=np.linalg.norm(positions[-1][end_index]-positions[0][first_index],axis=1)
closure={'matched_rows':len(end_index),'encoder_total_degrees':records[-1]['angle']-records[0]['angle'],
         'pixel_difference_median':float(np.median(pixel_delta)),
         'pixel_difference_p95':float(np.percentile(pixel_delta,95)),
         'camera_xyz_difference_median_mm':float(np.median(xyz_delta)),
         'camera_xyz_difference_p95_mm':float(np.percentile(xyz_delta,95)),
         'aligned_xyz_difference_median_mm':float(np.median(aligned_delta)),
         'aligned_xyz_difference_p95_mm':float(np.percentile(aligned_delta,95)),
         'meaning':'Same-run return repeatability only, not absolute dimensional accuracy or validation of calibration after pose change.'}
points=np.concatenate(cloud);display=np.concatenate(display_parts)
height_zero=float(display[:,1].min());display[:,1]-=height_zero
with (p/'fine_360_pointcloud.ply').open('w',encoding='ascii') as f:
    f.write(f'ply\nformat ascii 1.0\nelement vertex {len(points)}\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n')
    np.savetxt(f,points,fmt='%.6f %.6f %.6f %d %d %d')
np.savez(p/'fine_cloud_arrays.npz',camera_aligned_mm=points[:,:3],display_axis_frame_mm=display,rgb=points[:,3:],encoder_relative_degrees=np.array(angles))

# The mesh uses interpolation only between close measured rows, without caps or hole filling.
low=max(s[:,1].min() for s in samples);high=min(s[:,1].max() for s in samples)
levels=np.arange(np.ceil(low*4)/4,np.floor(high*4)/4+.001,.25)
grid=np.full((180,len(levels),3),np.nan)
for index,s in enumerate(samples):
    order=np.argsort(s[:,1]);h=s[order,1];xyz=s[order]
    unique=np.r_[True,np.diff(h)>1e-6];h=h[unique];xyz=xyz[unique]
    right=np.searchsorted(h,levels,side='right');right=np.clip(right,1,len(h)-1);left=right-1
    valid=(levels>=h[0])&(levels<=h[-1])&((h[right]-h[left])<.8)
    for k in range(3):grid[index,valid,k]=np.interp(levels[valid],h,xyz[:,k])
grid[:,:,1]-=height_zero
valid=np.isfinite(grid).all(2);ids=np.full(valid.shape,-1,dtype=int);ids[valid]=np.arange(valid.sum())
vertices=grid[valid];faces=[];skipped=0
join_seam=closure['aligned_xyz_difference_p95_mm']<1.0
for i in range(180 if join_seam else 179):
    ni=(i+1)%180
    for j in range(len(levels)-1):
        q=[ids[i,j],ids[ni,j],ids[ni,j+1],ids[i,j+1]]
        for tri in [(q[0],q[1],q[2]),(q[0],q[2],q[3])]:
            if min(tri)<0:skipped+=1;continue
            vv=vertices[list(tri)]
            if max(np.linalg.norm(vv[0]-vv[1]),np.linalg.norm(vv[1]-vv[2]),np.linalg.norm(vv[2]-vv[0]))>2.0:
                skipped+=1;continue
            normal=np.cross(vv[1]-vv[0],vv[2]-vv[0]);center=vv.mean(0)
            if normal@np.array([center[0],0,center[2]])<0:tri=(tri[0],tri[2],tri[1])
            faces.append(tri)
faces=np.array(faces,dtype=int)
# Map mesh back to the same camera reference coordinate system as the PLY point cloud.
mesh_camera=c+vertices[:,0,None]*ex+(vertices[:,1,None]+height_zero)*a+vertices[:,2,None]*ez
with (p/'fine_body_open_mesh.ply').open('w',encoding='ascii') as f:
    f.write(f'ply\nformat ascii 1.0\nelement vertex {len(mesh_camera)}\nproperty float x\nproperty float y\nproperty float z\nelement face {len(faces)}\nproperty list uchar int vertex_indices\nend_header\n')
    np.savetxt(f,mesh_camera,fmt='%.6f %.6f %.6f')
    for tri in faces:f.write('3 %d %d %d\n'%tuple(tri))
with (p/'fine_body_open_mesh.obj').open('w',encoding='ascii') as f:
    f.write('# Open side surface only. Millimeters. Not watertight; no fabricated top or bottom.\n')
    for v in mesh_camera:f.write('v %.6f %.6f %.6f\n'%tuple(v))
    for tri in faces+1:f.write('f %d %d %d\n'%tuple(tri))
np.savez(p/'fine_mesh_arrays.npz',display_vertices_mm=vertices,faces=faces)
summary={'status':'independent_fine_scan_reconstructed_for_shape_preview','reference_policy':cfg['comparison_policy'],
         'positions_including_closure':181,'pointcloud_profiles':180,'point_count':len(points),
         'closure':closure,'mesh':{'vertices':len(vertices),'triangles':len(faces),
             'skipped_triangles':skipped,'axial_interpolation_spacing_mm':.25,
             'max_interpolated_axial_gap_mm':.8,'max_triangle_edge_mm':2.0,
             'seam_joined':join_seam,'top_and_bottom_capped':False,'watertight':False},
         'measured_coordinate_extent_mm':np.ptp(display,axis=0).tolist(),
         'profiles':records,
         'calibration_files_sha256':{name:hashlib.sha256((p/name).read_bytes()).hexdigest() for name in ['laser_plane_v2_provisional.json','turntable_axis_v1_provisional.json']},
         'limitations':['Current pose is an independent acquisition reference; no strict comparison against coarse scan.',
             'Original provisional geometry reused after observed image shift; absolute dimensions are not validated.',
             'Only the body interior is scanned; bottom rim and top/bottom faces are not complete.',
             'Initial dark background reused across all angles.',
             'Raw point cloud is preserved separately; open mesh interpolates adjacent measured stripes and excludes long edges.',
             'Point colors indicate acquisition angle, not surface texture.']}
(p/'fine_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k!='profiles'},ensure_ascii=False,indent=2))
