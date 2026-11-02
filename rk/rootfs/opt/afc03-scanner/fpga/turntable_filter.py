"""Calibrated axis-height clipping; raw images and archived clouds are untouched."""
import json,math
import numpy as np

def load_filter(bundle,hashes):
 p=bundle/'turntable_filter.json'
 if not p.exists():return None
 cfg=json.loads(p.read_text())
 if cfg.get('enabled') is not True:return None
 if cfg.get('axis_sha256')!=hashes['axis_sha256']:raise ValueError('Turntable height profile belongs to a different axis calibration; recalibrate or disable it')
 h=cfg.get('min_axis_y_mm')
 if not isinstance(h,(int,float)) or isinstance(h,bool) or not math.isfinite(h) or abs(h)>1000:raise ValueError('Invalid turntable height cutoff')
 return cfg

def filter_mask(xyz,cfg):
 x=np.asarray(xyz)
 if cfg is None:return np.ones(len(x),bool),dict(enabled=False,removed_points=0)
 keep=x[:,1]>cfg['min_axis_y_mm']
 return keep,dict(enabled=True,method='axis_height',min_axis_y_mm=cfg['min_axis_y_mm'],input_points=len(x),removed_points=int((~keep).sum()),kept_points=int(keep.sum()),profile=cfg.get('profile',''))
