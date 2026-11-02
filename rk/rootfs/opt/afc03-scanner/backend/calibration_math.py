"""Hardware-free calibration solvers. Coordinates: full raw frame rotated CW90."""
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def object_points(cfg):
    cols,rows=cfg['pattern'];p=np.zeros((cols*rows,3),np.float64)
    p[:,:2]=np.mgrid[0:cols,0:rows].T.reshape(-1,2)*cfg['square_mm'];return p
def detect(raw,cfg):
    if raw is None or raw.shape!=(1080,1920,3):raise ValueError('需要 1920×1080 完整原图')
    image=cv2.rotate(raw,cv2.ROTATE_90_CLOCKWISE);gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    ok,c=cv2.findChessboardCornersSB(gray,tuple(cfg['pattern']),cv2.CALIB_CB_NORMALIZE_IMAGE|cv2.CALIB_CB_EXHAUSTIVE|cv2.CALIB_CB_ACCURACY)
    if not ok:raise ValueError('未检测到全部角点；原图保留，请调整棋盘格后重新采集')
    return c.reshape(-1,2),image
def pose(points,cfg,camera):
    K=np.array(camera['camera_matrix']);d=np.array(camera['distortion_coefficients']);obj=object_points(cfg)
    ok,rv,tv=cv2.solvePnP(obj,np.array(points,dtype=float),K,d)
    if not ok or tv[2,0]<=0:raise ValueError('棋盘格姿态无法求解')
    e=np.linalg.norm(cv2.projectPoints(obj,rv,tv,K,d)[0].reshape(-1,2)-points,axis=1)
    return rv.ravel(),tv.ravel(),float(np.sqrt(np.mean(e**2)))

def solve_camera(records,cfg):
    train=[r for r in records if not r['held_out']];test=[r for r in records if r['held_out']]
    if len(train)<8 or len(test)<2:raise ValueError('至少 8 张训练姿态、2 张独立验证姿态；建议 12–20 张覆盖不同位置和倾角')
    obj=object_points(cfg).astype(np.float32)
    rms,K,d,rvs,tvs=cv2.calibrateCamera([obj]*len(train),[np.array(r['corners'],np.float32) for r in train],(1080,1920),None,None,flags=cv2.CALIB_FIX_K3)
    result=dict(kind='camera',camera_matrix=K.tolist(),distortion_coefficients=d.ravel().tolist(),input_raw_size_wh=[1920,1080],calibration_image_size_wh=[1080,1920],preprocessing={'rotate_clockwise_degrees':90,'crop':False,'resize':False},pattern=cfg['pattern'],square_mm=cfg['square_mm'],rms_px=float(rms))
    checks=[]
    for r in records:
        _,_,e=pose(r['corners'],cfg,result);checks.append(dict(id=r['id'],held_out=r['held_out'],rms_px=e))
    normals=np.array([cv2.Rodrigues(rv)[0][:,2] for rv in rvs]);tilt=float(np.degrees(np.arccos(np.clip(normals@normals.T,-1,1))).max())
    centers=np.array([np.mean(r['corners'],axis=0) for r in train]);spread=np.ptp(centers,axis=0)/[1080,1920]
    worst=max(r['rms_px'] for r in checks if r['held_out'])
    plausible=200<K[0,0]<10000 and 200<K[1,1]<10000 and 0<K[0,2]<1080 and 0<K[1,2]<1920 and np.isfinite(d).all()
    result.update(per_view=checks,tilt_span_degrees=tilt,center_coverage_fraction=spread.tolist(),held_out_rms_max_px=worst,passed=bool(plausible and rms<1.0 and worst<1.5 and tilt>=10 and spread[0]>.15 and spread[1]>.15))
    result['review_reasons']=([label for ok,label in [(plausible,'内参范围不合理'),(rms<1,'训练误差需小于 1 px'),(worst<1.5,'验证误差需小于 1.5 px'),(tilt>=10,'训练倾角跨度需至少 10°'),(spread[0]>.15,'棋盘格中心左右跨度不足画面宽度的 15%'),(spread[1]>.15,'棋盘格中心上下跨度不足画面高度的 15%')] if not ok])
    return result

def laser_intersection(p,entry,cfg,camera):
    images={stage:cv2.rotate(cv2.imread(str(p/entry[stage])),cv2.ROTATE_90_CLOCKWISE) for stage in ['pattern','background','laser_on']}
    corners=np.array(entry['corners']);rv,tv,rms=pose(corners,cfg,camera)
    if rms>1.5:raise ValueError('棋盘格重投影误差过大')
    R=cv2.Rodrigues(rv)[0];normal=R[:,2];offset=normal@tv
    mask=np.zeros(images['pattern'].shape[:2],np.uint8);cv2.fillConvexPoly(mask,cv2.convexHull(corners.astype(np.float32)).astype(np.int32),255)
    mask=cv2.erode(mask,np.ones((15,15),np.uint8))
    signal=cv2.GaussianBlur(np.maximum(images['laser_on'].astype(np.float32)-images['background'].astype(np.float32),0).max(2),(5,1),0)
    points=[]
    for y in np.flatnonzero(mask.any(1)):
        valid=np.flatnonzero(mask[y]);row=signal[y];k=int(valid[np.argmax(row[valid])]);base=float(np.median(row[valid]));peak=row[k]-base
        if peak<18:continue
        lo=hi=k;threshold=base+max(6,.2*peak)
        while lo>valid[0] and row[lo-1]>threshold:lo-=1
        while hi<valid[-1] and row[hi+1]>threshold:hi+=1
        if lo==valid[0] or hi==valid[-1] or not 2<=hi-lo+1<=35 or images['laser_on'][y,lo:hi+1].max()>=250:continue
        x=np.arange(lo,hi+1);weights=np.maximum(row[x]-base,0);points.append([np.average(x,weights=weights),y])
    if len(points)<30:raise ValueError('有效激光点少于 30，请检查激光线、亮度和棋盘格范围')
    uv=np.array(points);K=np.array(camera['camera_matrix']);d=np.array(camera['distortion_coefficients'])
    rays=np.c_[cv2.undistortPoints(uv.reshape(-1,1,2),K,d).reshape(-1,2),np.ones(len(uv))]
    denom=rays@normal
    if np.any(np.abs(denom)<.05):raise ValueError('棋盘格与光线交角过小')
    xyz=rays*(offset/denom)[:,None]
    if not np.isfinite(xyz).all() or np.any(xyz[:,2]<=0):raise ValueError('无效激光交点')
    return xyz,{'id':entry['id'],'held_out':entry['held_out'],'points':len(xyz),'board_rms_px':rms,'board_normal':normal.tolist(),'board_offset_mm':float(offset)}

def fit_plane(groups,metadata,camera,camera_hash):
    train=[x for x,m in zip(groups,metadata) if not m['held_out']]
    test=[x for x,m in zip(groups,metadata) if m['held_out']]
    if len(train)<3 or len(test)<1:raise ValueError('至少 3 个训练平面及 1 个独立验证平面；需改变距离或倾角')
    # Equal weight per pose, preventing long stripes from overwhelming short ones.
    count=min(map(len,train));xyz=np.vstack([a[np.linspace(0,len(a)-1,count).astype(int)] for a in train])
    c=xyz.mean(0);_,sv,vt=np.linalg.svd(xyz-c,full_matrices=False);n=vt[-1];offset=float(n@c)
    if offset<0:n=-n;offset=-offset
    metrics=[]
    for points,m in zip(groups,metadata):metrics.append(dict(**m,p95_mm=float(np.percentile(np.abs(points@n-offset),95))))
    train95=max(m['p95_mm'] for m in metrics if not m['held_out']);test95=max(m['p95_mm'] for m in metrics if m['held_out'])
    spread=float(sv[1]/np.sqrt(len(xyz)))
    return dict(kind='laser',normal_camera=n.tolist(),offset_mm_n_dot_X_equals_offset=offset,camera=camera,camera_sha256=camera_hash,per_pose=metrics,training_p95_max_mm=train95,held_out_p95_max_mm=test95,second_spread_mm=spread,passed=bool(spread>=2 and train95<.5 and test95<1))

def solve_axis(records,cfg,camera,camera_hash):
    from scipy.optimize import least_squares
    train=[r for r in records if not r['held_out']];test=[r for r in records if r['held_out']]
    if len(train)<4 or len(test)<1:raise ValueError('至少 4 个训练角度及 1 个独立验证角度')
    base=train[0];rv,t0,_=pose(base['corners'],cfg,camera);R0=cv2.Rodrigues(rv)[0];zero=base['angle']
    vecs=[];blocks=[];rhs=[]
    for r in train[1:]:
        delta=np.radians(r['angle']-zero)
        if abs(delta)<.05:continue
        ri,ti,_=pose(r['corners'],cfg,camera);Q=cv2.Rodrigues(ri)[0]@R0.T
        vecs.append(cv2.Rodrigues(Q)[0].ravel()/delta);blocks.append(np.eye(3)-Q);rhs.append(ti-Q@t0)
    if len(vecs)<3 or np.ptp([r['angle'] for r in train])<30:raise ValueError('训练转角跨度不足 30°，或有效不同角度不足')
    n=np.mean(vecs,0);n/=np.linalg.norm(n)
    if abs(n[1])<.5:raise ValueError('转轴方向或角点顺序异常，请检查姿态')
    c=np.linalg.lstsq(np.vstack(blocks+[n.reshape(1,3)]),np.concatenate(rhs+[np.zeros(1)]),rcond=None)[0]
    # Signed y component preserves the encoder direction; it is not forced positive.
    sign=float(np.sign(n[1]))
    x0=np.r_[n[0]/abs(n[1]),n[2]/abs(n[1]),c[0],c[2],rv,t0]
    K=np.array(camera['camera_matrix']);d=np.array(camera['distortion_coefficients']);obj=object_points(cfg)
    def unpack(x):
        a=np.array([x[0],sign,x[1]]);a/=np.linalg.norm(a)
        center=np.array([x[2],-(a[0]*x[2]+a[2]*x[3])/a[1],x[3]])
        return a,center,cv2.Rodrigues(x[4:7])[0],x[7:10]
    def project(x,r):
        a,center,R,t=unpack(x);Q=cv2.Rodrigues(a*np.radians(r['angle']-zero))[0]
        xyz=(obj@R.T+t-center)@Q.T+center
        return cv2.projectPoints(xyz,np.zeros(3),np.zeros(3),K,d)[0].reshape(-1,2)
    def residual(x):return np.concatenate([(project(x,r)-r['corners']).ravel() for r in train])
    fit=least_squares(residual,x0,x_scale='jac',max_nfev=200,ftol=1e-11,xtol=1e-11,gtol=1e-9)
    a,c,_,_=unpack(fit.x);metrics=[]
    for r in records:
        error=np.linalg.norm(project(fit.x,r)-r['corners'],axis=1)
        metrics.append(dict(id=r['id'],held_out=r['held_out'],angle=r['angle'],rms_px=float(np.sqrt(np.mean(error**2)))))
    train_rms=float(np.sqrt(np.mean(residual(fit.x)**2)*2));test_rms=max(r['rms_px'] for r in metrics if r['held_out'])
    return dict(kind='axis',axis_direction_for_positive_encoder_camera=a.tolist(),axis_point_closest_to_camera_origin_mm=c.tolist(),encoder_zero_degrees=zero,camera_sha256=camera_hash,training_rms_px=train_rms,held_out_rms_max_px=test_rms,per_view=metrics,passed=bool(fit.success and np.isfinite(fit.x).all() and train_rms<1.5 and test_rms<2))

def solve_session(p):
    p=Path(p);cfg=read(p/'scan_config.json');records=read(p/'captures.json');kind=cfg['kind']
    if kind=='camera':result=solve_camera(records,cfg)
    else:
        camera=read(p/'camera.json');hash_value=digest(p/'camera.json')
        if kind=='axis':result=solve_axis(records,cfg,camera,hash_value)
        else:
            groups=[];metadata=[]
            for r in records:
                xyz,m=laser_intersection(p,r,cfg,camera);groups.append(xyz);metadata.append(m)
            result=fit_plane(groups,metadata,camera,hash_value)
    result.update(schema_version=1,source_session=p.name,absolute_accuracy_validated=False,thresholds_are_operational=True)
    if 'review_reasons' not in result and not result['passed']:
        result['review_reasons']=['激光训练 P95 需 <0.5 mm、独立验证 P95 <1 mm，第二方向展开需 ≥2 mm' if kind=='laser' else '转轴训练 RMS 需 <1.5 px、独立验证 RMS <2 px，并成功收敛']
    return result
