"""Offline, visibility-aware photo evidence. Never changes acquisition assets.

Rigid view transforms are recovered from the archived matched camera/axis XYZ,
not estimated from object appearance. Their held-out pixel residual is checked.
"""
from pathlib import Path
import json, hashlib, warnings
import numpy as np
import cv2
from numba import njit
from skimage.segmentation import slic

ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parent
ARCHIVES={
 'duck':PROJECT/'fpga-scan-20261002/fpga-full-20261003-005504/source',
 'doll':Path('F:/AAA_FPGA/scan3d-pc-archives/scan3d-pc-20261010-032157-5c3bcd'),
 'duck-last':Path('E:/SCAN3D/scan3d-pc-archives/scan3d-pc-20261010-163204-441887'),
 'cat':ROOT/'assets/cat-photo-source',
}
VERSION='photo-evidence-v2'

def rigid(x,y):
    u,_,vt=np.linalg.svd((x-x.mean(0)).T@(y-y.mean(0)))
    correction=np.eye(3);correction[2,2]=np.linalg.det(u@vt)
    r=u@correction@vt;t=y.mean(0)-x.mean(0)@r
    return r,t

@njit(cache=True)
def raster(uv,z,faces,w,h):
    depth=np.full((h,w),1e9,np.float32)
    for tri in faces:
        a,b,c=uv[tri[0]],uv[tri[1]],uv[tri[2]]
        za,zb,zc=z[tri[0]],z[tri[1]],z[tri[2]]
        if min(za,zb,zc)<=0:continue
        den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(den)<1e-8:continue
        for y in range(max(0,int(np.floor(min(a[1],b[1],c[1])))),min(h,int(np.ceil(max(a[1],b[1],c[1])))+1)):
            for x in range(max(0,int(np.floor(min(a[0],b[0],c[0])))),min(w,int(np.ceil(max(a[0],b[0],c[0])))+1)):
                aa=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/den
                bb=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/den;cc=1-aa-bb
                if min(aa,bb,cc)<-1e-5:continue
                zz=1/(aa/za+bb/zb+cc/zc)
                if zz<depth[y,x]:depth[y,x]=zz
    return depth

def projection(x,k,d):
    return cv2.projectPoints(np.asarray(x,np.float64),np.zeros(3),np.zeros(3),k,d)[0].reshape(-1,2)

def view_transform(folder,k,d):
    pairs=[]
    for label in 'AB':
        p=folder/label/'points.npz'
        if not p.exists():continue
        with np.load(p,allow_pickle=False) as z:
            if len(z['uv']):pairs.append((z['axis_frame_mm'],z['camera_xyz_mm'],z['uv']))
    if not pairs:return None
    x,y,uv=[np.concatenate([p[i] for p in pairs]) for i in range(3)]
    if len(x)<20 or np.linalg.matrix_rank(x-x.mean(0))<3:return None
    train=np.arange(len(x))%2==0;r,t=rigid(x[train],y[train])
    err=np.linalg.norm(projection(x[~train]@r+t,k,d)-uv[~train],axis=1)
    residual=float(np.percentile(err,95))
    if residual>.25:raise ValueError(f'{folder}: archived coordinate projection residual {residual}')
    return r,t,residual

def weighted_quantile(values,weights,q):
    order=np.argsort(values,axis=0)
    v=np.take_along_axis(values,order,axis=0);w=np.take_along_axis(weights,order,axis=0)
    idx=(np.cumsum(w,axis=0)<q*w.sum(0)).sum(0).clip(0,len(values)-1)
    return v[idx,np.arange(values.shape[1])]

def photo_evidence(item,vertices,faces,out,views=48):
    archive=ARCHIVES.get(item['id'])
    if archive is None or not (archive/'bundle/camera.json').exists():return None
    out.mkdir(exist_ok=True)
    cam_path=archive/'bundle/camera.json';cam=json.loads(cam_path.read_text())
    k=np.array(cam['camera_matrix']);d=np.array(cam['distortion_coefficients'])
    dirs=sorted((p for p in archive.glob('position-*') if (p/'COLOR/same-frame.png').exists()),key=lambda p:int(p.name.split('-')[-1]))
    chosen=[dirs[i] for i in np.unique(np.linspace(0,len(dirs)-2,min(views,len(dirs)-1),dtype=int))]
    signature=hashlib.sha256((VERSION+item['geometry_key']+cam_path.read_text()+''.join(str(p)+(str((p/'COLOR/same-frame.png').stat().st_mtime_ns)) for p in chosen)).encode()).hexdigest()
    cache=ROOT/'assets'/f'{item["id"]}-photo-evidence.npz'
    if cache.exists():
        with np.load(cache) as z:
            if str(z['signature'])==signature:return {q:z[q] for q in z.files if q!='signature'}
    cv2.setNumThreads(2)
    world=vertices@np.array(item['transform']['rotation']).T+np.array(item['transform']['origin'])
    centers=world[faces].mean(1)
    normals=np.cross(world[faces[:,1]]-world[faces[:,0]],world[faces[:,2]]-world[faces[:,0]])
    normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-10)
    all_colors=[];all_weight=[];all_contrast=[];records=[]
    for index,folder in enumerate(chosen):
        tr=view_transform(folder,k,d)
        if tr is None:continue
        r,t,residual=tr
        im=cv2.rotate(cv2.cvtColor(cv2.imread(str(folder/'COLOR/same-frame.png')),cv2.COLOR_BGR2RGB),cv2.ROTATE_90_CLOCKWISE)
        vh,vw=im.shape[:2];vc=world@r+t;fc=centers@r+t
        uv=projection(vc,k,d);fcuv=projection(fc,k,d)
        # Undistorted virtual camera makes triangle raster depth geometrically exact.
        undistorted=cv2.undistortPoints(uv[:,None],k,d,P=k).reshape(-1,2)
        fcu=cv2.undistortPoints(fcuv[:,None],k,d,P=k).reshape(-1,2)
        depth=raster(undistorted.astype(np.float64),vc[:,2],faces,vw,vh)
        pix=np.rint(fcuv).astype(int);px=np.rint(fcu).astype(int)
        inside=(pix[:,0]>=2)&(pix[:,0]<vw-2)&(pix[:,1]>=2)&(pix[:,1]<vh-2)&(px[:,0]>=0)&(px[:,0]<vw)&(px[:,1]>=0)&(px[:,1]<vh)
        pix[:,0]=pix[:,0].clip(0,vw-1);pix[:,1]=pix[:,1].clip(0,vh-1)
        px[:,0]=px[:,0].clip(0,vw-1);px[:,1]=px[:,1].clip(0,vh-1)
        view=-fc/np.linalg.norm(fc,axis=1)[:,None];facing=np.sum((normals@r)*view,axis=1)
        good=inside&(facing>.3)&(np.abs(fc[:,2]-depth[px[:,1],px[:,0]])<.45)
        # Crop processing to the model silhouette. SLIC suppresses noise only in
        # flat regions; high contrast features retain their original pixel values.
        x0,y0=np.maximum(np.floor(uv.min(0)-6).astype(int),[0,0]);x1,y1=np.minimum(np.ceil(uv.max(0)+7).astype(int),[vw,vh])
        crop=im[y0:y1,x0:x1]; smooth=cv2.bilateralFilter(crop,5,18,3)
        sp=slic(smooth,n_segments=max(100,crop.shape[0]*crop.shape[1]//64),compactness=7,start_label=0,channel_axis=-1)
        count=np.bincount(sp.ravel());means=np.array([np.bincount(sp.ravel(),weights=smooth[:,:,j].ravel())/count for j in range(3)]).T
        flat=means[sp].astype(np.float32);delta=np.linalg.norm(flat-smooth,axis=2)
        filtered=np.where((delta<12)[:,:,None],.7*smooth+.3*flat,smooth).astype(np.uint8)
        full=im.copy();full[y0:y1,x0:x1]=filtered
        color=np.concatenate([cv2.remap(full,chunk[:,0].astype(np.float32).reshape(-1,1),chunk[:,1].astype(np.float32).reshape(-1,1),cv2.INTER_LINEAR).reshape(-1,3) for chunk in np.array_split(fcuv,max(1,int(np.ceil(len(fcuv)/16000))))]).astype(np.float32)
        labs=cv2.cvtColor(crop.astype(np.float32)/255,cv2.COLOR_RGB2LAB)
        # Local closing is a brightness baseline, not a region label.
        base=cv2.morphologyEx(labs[:,:,0],cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(31,31)))
        local_contrast=np.zeros(len(faces),np.float32)
        ii=np.flatnonzero(good);xx=pix[ii,0]-x0;yy=pix[ii,1]-y0
        keep=(xx>=0)&(xx<x1-x0)&(yy>=0)&(yy<y1-y0);ii=ii[keep];xx=xx[keep];yy=yy[keep]
        local_contrast[ii]=base[yy,xx]-labs[yy,xx,0]
        good &= (color.max(1)<250)&(color.max(1)>8)
        weight=np.where(good,facing.clip(0,1)**4,0).astype(np.float32)
        all_colors.append(color);all_weight.append(weight);all_contrast.append(local_contrast)
        records.append(dict(position=folder.name,image=str(folder/'COLOR/same-frame.png'),image_sha256=hashlib.sha256((folder/'COLOR/same-frame.png').read_bytes()).hexdigest(),held_out_projection_p95_px=residual,visible_faces=int(good.sum())))
        if index%8==0:
            # Real source image and projected mesh outline for audit (not fake texture).
            # draw only outer silhouette from depth in the calibrated undistorted frame
            mask=(depth<1e8).astype(np.uint8)*255
            un=cv2.undistort(im,k,d);contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(un,contours,-1,(30,200,110),1)
            cv2.imwrite(str(out/f'projection-{index:02d}.jpg'),cv2.cvtColor(un[max(0,y0-10):min(vh,y1+10),max(0,x0-10):min(vw,x1+10)],cv2.COLOR_RGB2BGR))
        print(f'{item["id"]}: photo {index+1}/{len(chosen)} {folder.name}',flush=True)
    rgb=np.array(all_colors);weights=np.array(all_weight);contrasts=np.array(all_contrast)
    # Restrict fusion to the best-facing observations; then robust per-channel
    # weighted medians prevent a boundary-straddling view tinting every view.
    cutoff=weights.max(0)*.45;weights[weights<cutoff]=0
    valid=(weights>0).sum(0)>=3
    colors=np.array([weighted_quantile(rgb[:,:,j],weights,.55) for j in range(3)]).T
    contrast=weighted_quantile(contrasts,weights,.5)
    confidence=(weights>0).sum(0)
    result=dict(colors=colors,valid=valid,contrast=contrast,observations=confidence,metadata=np.array(json.dumps(dict(version=VERSION,archive=str(archive),views=records,settings=dict(view_count=views,minimum_views=3,facing_min=.3,visibility_depth_mm=.45,top_view_weight_ratio=.45,slic_compactness=7,slic_area_px=64),held_out_projection_max_p95_px=max(q['held_out_projection_p95_px'] for q in records)))))
    np.savez_compressed(cache,signature=signature,**result)
    return result
