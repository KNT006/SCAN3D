"""Calibrated radial workspace; immutable per-run config, shared by A/B."""
import math
import json
import numpy as np

DEFAULT = dict(version=1, enabled=False, radius_mm=90., margin_mm=0.)

def validate(cfg):
    if not isinstance(cfg,dict) or set(cfg)-set(DEFAULT)-{'axis_sha256'}:
        raise ValueError('无效空间过滤配置')
    p=dict(DEFAULT,**cfg)
    if p['version']!=1 or type(p['enabled']) is not bool:raise ValueError('无效空间过滤版本或开关')
    for k,low,high in [('radius_mm',5,200),('margin_mm',0,30)]:
        x=p[k]
        if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or not low<=x<=high:
            raise ValueError(k+' 超出允许范围')
        p[k]=float(x)
    if 'axis_sha256' in p and (not isinstance(p['axis_sha256'],str) or len(p['axis_sha256'])!=64):raise ValueError('无效转轴标定标识')
    return p

def load(bundle,axis_hash):
    path=bundle/'spatial_filter.json'
    if not path.exists():return dict(DEFAULT)
    cfg=validate(json.loads(path.read_text(encoding='utf-8')))
    if cfg['enabled'] and cfg.get('axis_sha256')!=axis_hash:raise ValueError('空间范围与当前转轴标定不匹配')
    return cfg

def radial_mask(xyz,cfg):
    p=validate(cfg);xyz=np.asarray(xyz,float).reshape(-1,3)
    radius=np.hypot(xyz[:,0],xyz[:,2])
    keep=np.isfinite(radius)&(radius<=p['radius_mm']+p['margin_mm'])
    if not p['enabled']:keep=np.ones(len(xyz),bool)
    return keep,radius,dict(p,effective_radius_mm=p['radius_mm']+p['margin_mm'],input_points=len(xyz),removed_points=int((~keep).sum()),kept_points=int(keep.sum()),method='axis_radial_cylinder')

def supported(uv,valid,settings=None):
    p=dict(neighbor_rows=4,min_support=3,dx_intercept=2,dx_per_row=3)
    if settings:p.update({k:settings[k] for k in p if k in settings})
    rows={}
    for j,(x,y) in enumerate(uv):
        if valid[j]:rows.setdefault(int(y),[]).append(float(x))
    return np.array([bool(valid[j] and sum(any(abs(xx-x)<=p['dx_intercept']+p['dx_per_row']*abs(dy) for xx in rows.get(int(y)+dy,[])) for dy in range(-p['neighbor_rows'],p['neighbor_rows']+1) if dy)>=p['min_support']) for j,(x,y) in enumerate(uv)],bool)
