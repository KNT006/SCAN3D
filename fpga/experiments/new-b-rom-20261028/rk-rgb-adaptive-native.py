"""ABI6 sparse candidates: calibrated spatial gate + local RGB threshold.
No raw laser image extraction is performed here. COLOR is the same-angle raw
RGB exposure, before display color correction. Fixed-40 winners are frozen.
"""
from pathlib import Path
import json,time
import numpy as np
from row_results import require,ADAPTIVE_ALGORITHM
from rk_stripe_strategy import Frame
ALGORITHM=ADAPTIVE_ALGORITHM
VERSION='rk-ground-first-near20-single-peak-v2'
SETTINGS=dict(radius_mm=70.,signal_min=40,adaptive_min=25,dark_v=100,bright_v=160,
    prominence=18,distance=8,width_max=100,weak_width_max=65,weak_signal=80,
    core_fraction=.7,core_radius=10,neighbor_rows=4,min_support=3,weak_support=4,
    adaptive_width=25,dx_intercept=2,dx_per_row=3,noise_gate=False)
HASHES=dict(axis_sha256='aaad2d0409f0d6b59f64c23e4ef7ee32f9ec75941b480fb7fb7f0c0ffc21014b',
 camera_sha256='32ef6bc57b8ef02cf0043ecb657ae2fbad72dc12bb0653d787c7e93c8884f8d1',
 planes_sha256='4219e460decd036b1d0afd9049601c4bb8e18f151a776e9e32b9afb9aa319d61')
def validate_profile(context):
 require(context['algorithm']==ALGORITHM,'ABI6 requires the spatial/RGB strategy')
 require(all(context['calibration'].get(k)==v for k,v in HASHES.items()),'Calibration changed: rebuild FPGA spatial ROM before scanning')
 g=context['geometry']
 require(g['processing_size_wh']==[1080,1920] and g['rotation_cw']==90 and g['global_x_origin']==0 and g['row_input_width']==1080,'Unsupported spatial ROM image geometry')
 require(context['laser_id'] in ('A','B'),'Spatial mask needs an explicit single-laser identity')

def threshold(color,y,k):
 patch=color[max(0,y-3):y+4,max(0,k-3):k+4].reshape(-1,3).astype(float)
 rgb=np.median(patch,axis=0);v=float(rgb.max());spread=float(np.percentile(np.max(np.abs(patch-rgb),axis=1),90))
 reliable=12<=v<245 and spread<=35
 suggested=int(np.floor(25+15*np.clip((v-100)/60,0,1)+.5))
 return dict(rgb=rgb.tolist(),v=v,color_spread=spread,color_reliable=bool(reliable),color_threshold=suggested,threshold=suggested if reliable else 40)

def color_thresholds(color,records):
 if not records:return []
 ys=np.array([r['y'] for r in records]);xs=np.array([r['k'] for r in records])
 if np.any((ys<3)|(ys>=1917)|(xs<3)|(xs>=1077)):
  return [threshold(color,int(y),int(x)) for y,x in zip(ys,xs)]
 # Same 49 samples and exact median/percentile as the scalar oracle.
 dy,dx=np.mgrid[-3:4,-3:4]
 patches=color[ys[:,None]+dy.ravel(),xs[:,None]+dx.ravel()].astype(float)
 rgb=np.median(patches,axis=1);v=rgb.max(axis=1)
 spread=np.percentile(np.max(np.abs(patches-rgb[:,None,:]),axis=2),90,axis=1)
 reliable=(v>=12)&(v<245)&(spread<=35)
 suggested=np.floor(25+15*np.clip((v-100)/60,0,1)+.5).astype(int)
 return [dict(rgb=rgb[i].tolist(),v=float(v[i]),color_spread=float(spread[i]),color_reliable=bool(reliable[i]),color_threshold=int(suggested[i]),threshold=int(suggested[i]) if reliable[i] else 40) for i in range(len(records))]

def supporters(r,rows):
 return [r['y']+dy for dy in range(-4,5) if dy and any(abs(q['x']-r['x'])<=2+3*abs(dy) for q in rows.get(r['y']+dy,[]))]
def byrow(records):
 rows={}
 for r in records:rows.setdefault(r['y'],[]).append(r)
 return rows

def continuous(records):
 rows=byrow(records)
 return [r for r in records if len(supporters(r,rows))>=3]

def process_frame(frame,adapter,output=None,color=None):
 from rk_candidate_policy import select_candidates,VERSION
 header=frame.header;validate_profile(header)
 require(isinstance(color,np.ndarray) and color.dtype==np.uint8 and color.shape==(1920,1080,3),'Same-angle raw COLOR RGB frame required')
 require(adapter.hashes==HASHES,'Spatial calibration bundle mismatch')
 cfg=adapter.spatial_filter
 require(cfg['enabled'] and float(cfg['radius_mm'])==70 and float(cfg.get('margin_mm',0))==0,'FPGA ROM requires radius 70 mm without margin')
 raw=[]
 for c in frame.centers:
  require(c.peak_x is not None and c.strength is not None,'Incomplete FPGA candidate metadata')
  raw.append(dict(x=c.num/c.den,y=c.row,k=c.peak_x,peak32=c.strength,lo=c.lo,hi=c.hi,width=c.hi-c.lo+1,signalmax=c.peak32&255,saturated=(c.peak32>>8)&1))
 for r,t in zip(raw,color_thresholds(color,raw)):r.update(t)
 new_header=dict(header,algorithm=VERSION,protocol='afc03.rk-stripes.v1')
 arrays,report,records=select_candidates(raw,new_header,adapter)
 report.update(execution='FPGA candidates; RK ground-first near20 filtering; long-track advisory only',stripe_settings=SETTINGS,source_frame_id=header['source_frame_id'],raw_images_preserved=True,raw_images_read_for_extraction=False,color_patch_size=7,noise_gate=False)
 if output:
  output=Path(output)
  np.savez_compressed(output/'strategy-candidates.npz',uv=np.array([[r['x'],r['y']] for r in records]).reshape(-1,2),signal=np.array([r['signalmax'] for r in records]),width=np.array([r['width'] for r in records]),threshold=np.array([r['threshold'] for r in records]))
  (output/'strategy.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
  (output/'strategy-candidates.json').write_text(json.dumps(records,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
 return arrays,report,new_header
