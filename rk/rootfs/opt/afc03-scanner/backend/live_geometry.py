"""Recorded full-frame laser profiles to geometry; no hardware access."""
import colorsys
import json
from pathlib import Path
import cv2
import numpy as np


def write_json(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def stripe(image, background, roi):
    x0, y0, x1, y1 = roi
    signal = cv2.subtract(image[y0:y1,x0:x1], background[y0:y1,x0:x1]).max(2)
    points, widths = [], []
    rejected = dict(weak=0, width=0, saturated=0)
    for y in range(y0, y1):
        row = signal[y-y0].astype(float)
        k = int(row.argmax()); peak = row[k]
        if peak < 18:
            rejected['weak'] += 1; continue
        lo = hi = k; threshold = max(10, peak*.45)
        while lo > 0 and row[lo-1] >= threshold: lo -= 1
        while hi+1 < len(row) and row[hi+1] >= threshold: hi += 1
        if not 2 <= hi-lo+1 <= 35:
            rejected['width'] += 1; continue
        if image[y, x0+lo:x0+hi+1].max() >= 250:
            rejected['saturated'] += 1; continue
        weights = row[lo:hi+1]
        points.append([x0+np.dot(np.arange(lo, hi+1), weights)/weights.sum(), y])
        widths.append(hi-lo+1)
    return np.array(points).reshape(-1, 2), np.array(widths), rejected


def repeat_error(uv, other):
    mapping = {int(y): x for x, y in other}
    delta = [abs(x-mapping[int(y)]) for x,y in uv if int(y) in mapping]
    return dict(matched=len(delta), median=float(np.median(delta)) if delta else None,
                p95=float(np.percentile(delta,95)) if delta else None)


def stable_rows(uv, other, max_difference):
    mapping={int(y):x for x,y in other}
    return np.array([int(y) in mapping and abs(x-mapping[int(y)])<=max_difference for x,y in uv],dtype=bool)


def closure_passes(closure):
    value=closure.get('p95_mm')
    return closure.get('matched_rows',0)>=40 and value is not None and np.isfinite(value) and value<1.0


def calibration(path):
    laser = json.loads((path/'laser_plane_v2_provisional.json').read_text())
    axis = json.loads((path/'turntable_axis_v1_provisional.json').read_text())
    K = np.array(laser['camera']['camera_matrix'])
    dist = np.array(laser['camera']['distortion_coefficients'])
    n = np.array(laser['normal_camera']); d = laser['offset_mm_n_dot_X_equals_offset']
    a = np.array(axis['axis_direction_for_positive_encoder_camera'])
    c = np.array(axis['axis_point_closest_to_camera_origin_mm'])
    ex = np.array([1.,0,0]); ex -= a*(ex@a); ex /= np.linalg.norm(ex)
    return K, dist, n, d, a, c, ex, np.cross(ex,a)


def ply(path, xyz, rgb, faces=None):
    with path.open('w', encoding='ascii') as f:
        f.write(f'ply\nformat ascii 1.0\ncomment Units mm; provisional calibration; open measured surface\nelement vertex {len(xyz)}\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\n')
        if faces is not None: f.write(f'element face {len(faces)}\nproperty list uchar int vertex_indices\n')
        f.write('end_header\n')
        np.savetxt(f, np.column_stack((xyz,rgb)), fmt='%.6f %.6f %.6f %d %d %d')
        if faces is not None:
            for tri in faces: f.write('3 %d %d %d\n'%tuple(tri))


def reconstruct(path, check=lambda: None):
    cfg = json.loads((path/'scan_config.json').read_text())
    count = cfg['intervals']; start = cfg['start_encoder_degrees']
    K,dist,n,d,a,c,ex,ez = calibration(path)
    camera, displays, colors, profiles = [], [], [], []
    for i in range(count+1):
        check(); label=f'position{i:03d}'
        with np.load(path/(label+'_stripe.npz')) as profile:
            uv=profile['uv']
            if cfg.get('repeat_filter_px') is not None:
                uv=uv[stable_rows(uv,profile['repeat_uv'],cfg['repeat_filter_px'])]
        record = json.loads((path/(label+'_record.json')).read_text())
        if record['status'] != 'captured_and_verified': raise ValueError('Unverified capture')
        xy = cv2.undistortPoints(uv[:,None,:],K,dist).reshape(-1,2) if len(uv) else np.empty((0,2))
        rays = np.column_stack((xy,np.ones(len(xy)))); denom=rays@n
        safe = denom > .05; rays=rays[safe]; uv=uv[safe]; denom=denom[safe]
        xyz = rays*(d/denom)[:,None]
        h=(xyz-c)@a; radius=np.linalg.norm(xyz-c-h[:,None]*a,axis=1)
        valid=(xyz[:,2]>80)&(xyz[:,2]<350)&(radius<90)&np.isfinite(xyz).all(1)
        uv=uv[valid]; xyz=xyz[valid]; angle=record['motion']['after']
        R=cv2.Rodrigues(a*np.deg2rad(angle-start))[0]; aligned=(xyz-c)@R+c
        v=aligned-c; display=np.column_stack((v@ex,v@a,v@ez))
        np.savez(path/(label+'_reconstruction.npz'),uv=uv,camera_xyz_mm=xyz,aligned_xyz_mm=aligned,axis_frame_mm=display,encoder_degrees=angle)
        profiles.append(dict(index=i,points=len(uv),angle=angle))
        if i<count:
            camera.append(aligned); displays.append(display)
            color=np.rint(np.array(colorsys.hsv_to_rgb(i/count*.8,.65,.9))*255)
            colors.append(np.tile(color,(len(xyz),1)))
    xyz=np.concatenate(camera); disp=np.concatenate(displays); rgb=np.concatenate(colors)
    if len(xyz)<100: raise ValueError('Too few reconstructed points')
    zero=float(disp[:,1].min()); disp[:,1]-=zero
    np.savez(path/'fine_cloud_arrays.npz',camera_aligned_mm=xyz,display_axis_frame_mm=disp,rgb=rgb)
    ply(path/'fine_360_pointcloud.ply',xyz,rgb)
    first=np.load(path/'position000_reconstruction.npz'); last=np.load(path/f'position{count:03d}_reconstruction.npz')
    mapping={int(y):j for j,(_,y) in enumerate(first['uv'])}
    end=[j for j,(_,y) in enumerate(last['uv']) if int(y) in mapping]
    begin=[mapping[int(last['uv'][j,1])] for j in end]
    delta=np.linalg.norm(last['aligned_xyz_mm'][end]-first['aligned_xyz_mm'][begin],axis=1)
    closure=dict(matched_rows=len(delta),p95_mm=float(np.percentile(delta,95)) if len(delta) else None,
                 meaning='Return repeatability, not absolute accuracy')
    # Union of measured heights; missing rows remain holes. Never close top/bottom.
    levels=np.arange(np.ceil(zero*4)/4,np.floor(max(s[:,1].max() for s in displays if len(s))*4)/4+.001,.25)
    grid=np.full((count,len(levels),3),np.nan)
    for i,s in enumerate(displays):
        check()
        if len(s)<2: continue
        order=np.argsort(s[:,1]); s=s[order]; keep=np.r_[True,np.diff(s[:,1])>1e-6]; s=s[keep]; h=s[:,1]
        if len(h)<2: continue
        right=np.clip(np.searchsorted(h,levels,side='right'),1,len(h)-1); left=right-1
        valid=(levels>=h[0])&(levels<=h[-1])&((h[right]-h[left])<.8)
        for k in range(3): grid[i,valid,k]=np.interp(levels[valid],h,s[:,k])
    grid[:,:,1]-=zero; mask=np.isfinite(grid).all(2); ids=np.full(mask.shape,-1,int); ids[mask]=np.arange(mask.sum())
    vertices=grid[mask]; faces=[]; seam=len(delta)>=40 and closure['p95_mm']<1
    for i in range(count if seam else count-1):
        check(); ni=(i+1)%count
        for j in range(len(levels)-1):
            q=[ids[i,j],ids[ni,j],ids[ni,j+1],ids[i,j+1]]
            for tri in ((q[0],q[1],q[2]),(q[0],q[2],q[3])):
                if min(tri)<0: continue
                vv=vertices[list(tri)]
                if max(np.linalg.norm(vv[k]-vv[(k+1)%3]) for k in range(3))>2: continue
                normal=np.cross(vv[1]-vv[0],vv[2]-vv[0]); center=vv.mean(0)
                if normal@np.array([center[0],0,center[2]])<0: tri=(tri[0],tri[2],tri[1])
                faces.append(tri)
    faces=np.array(faces,int).reshape(-1,3); mesh_camera=c+vertices[:,0,None]*ex+(vertices[:,1,None]+zero)*a+vertices[:,2,None]*ez
    mesh_rgb=np.array([colorsys.hsv_to_rgb(i/count*.8,.65,.9) for i,j in np.argwhere(mask)])*255
    ply(path/'fine_body_open_mesh.ply',mesh_camera,mesh_rgb,faces)
    np.savez(path/'fine_mesh_arrays.npz',display_vertices_mm=vertices,camera_vertices_mm=mesh_camera,faces=faces,profile_level_indices=np.argwhere(mask),levels=levels,height_zero=zero)
    summary=dict(point_count=len(xyz),triangle_count=len(faces),positions=count+1,closure=closure,calibration='provisional',watertight=False,profiles=profiles)
    write_json(path/'fine_summary.json',summary)
    return summary


def colorize(path, check=lambda: None):
    cfg=json.loads((path/'scan_config.json').read_text()); count=cfg['intervals']
    K,dist,n,d,a,c,ex,ez=calibration(path); colors=[]; profile_colors=[]
    for i in range(count+1):
        check(); label=f'position{i:03d}'; geo=np.load(path/(label+'_reconstruction.npz'))
        record=json.loads((path/'color'/(label+'_record.json')).read_text())
        residual=record['motion']['after']-(float(geo['encoder_degrees'])-360)
        if abs(residual)>.35: raise ValueError('Color and geometry angle mismatch')
        xyz=(geo['camera_xyz_mm']-c)@cv2.Rodrigues(a*np.deg2rad(residual))[0].T+c
        if len(xyz):
            uv=cv2.projectPoints(xyz,np.zeros(3),np.zeros(3),K,dist)[0].reshape(-1,2).astype(np.float32)
            if not ((uv>=0).all() and (uv[:,0]<1079).all() and (uv[:,1]<1919).all()): raise ValueError('Color projection outside frame')
            pair=[]
            for suffix in ['color','color_repeat']:
                im=cv2.rotate(cv2.imread(str(path/'color'/(label+'_'+suffix+'.png'))),cv2.ROTATE_90_CLOCKWISE)
                pair.append(cv2.remap(im,uv[:,0,None],uv[:,1,None],cv2.INTER_LINEAR).reshape(-1,3)[:,::-1].astype(float))
            rgb=np.rint((pair[0]+pair[1])/2).astype(np.uint8)
        else: rgb=np.empty((0,3),np.uint8)
        if i<count: colors.append(rgb); profile_colors.append((geo['axis_frame_mm'],rgb))
    cloud=np.load(path/'fine_cloud_arrays.npz'); rgb=np.concatenate(colors)
    ply(path/'fine_360_colored_pointcloud.ply',cloud['camera_aligned_mm'],rgb)
    np.savez(path/'colored_cloud_arrays.npz',camera_aligned_mm=cloud['camera_aligned_mm'],display_axis_frame_mm=cloud['display_axis_frame_mm'],rgb=rgb)
    mesh=np.load(path/'fine_mesh_arrays.npz'); indices=mesh['profile_level_indices']; levels=mesh['levels']; mesh_rgb=np.zeros((len(indices),3))
    for i,(s,color) in enumerate(profile_colors):
        selected=indices[:,0]==i
        if not selected.any(): continue
        order=np.argsort(s[:,1]); h=s[order,1]; color=color[order]; unique=np.r_[True,np.diff(h)>1e-6]; h=h[unique]; color=color[unique]
        for k in range(3): mesh_rgb[selected,k]=np.interp(levels[indices[selected,1]],h,color[:,k])
    ply(path/'fine_body_colored_mesh.ply',mesh['camera_vertices_mm'],np.rint(mesh_rgb),mesh['faces'])
    write_json(path/'color_summary.json',dict(point_count=len(rgb),source='laser-off photographs',angle_corrected=True))
