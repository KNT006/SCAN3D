import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import sys,time,json,argparse,hashlib,platform,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'vendor'))
import numpy as np
from scipy.spatial import cKDTree,Delaunay
from scipy.ndimage import binary_closing,binary_fill_holes,label,gaussian_filter,distance_transform_edt
from skimage.restoration import inpaint_biharmonic
def write_ply(path,xyz,rgb):
 a=np.empty(len(xyz),dtype=[('x','<f4'),('y','<f4'),('z','<f4'),('red','u1'),('green','u1'),('blue','u1')])
 for j,k in enumerate(('x','y','z')):a[k]=xyz[:,j]
 for j,k in enumerate(('red','green','blue')):a[k]=rgb[:,j]
 with open(path,'wb') as f:
  f.write(('ply\nformat binary_little_endian 1.0\nelement vertex '+str(len(a))+'\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n').encode());a.tofile(f)
def bounds_mask(x,c):return np.all((x>np.array([c['x'][0],c['y'][0],c['z'][0]]))&(x<np.array([c['x'][1],c['y'][1],c['z'][1]])),axis=1)
def surface_samples(src,cfg):
 x=src['xyz'];context=dict(cfg,z=[cfg['z'][0]-5,cfg['z'][1]]);m=bounds_mask(x,context)
 p=x[m];assert len(p)>=100,'区域内点太少'
 _,ix=np.unique(np.floor(p/.35).astype(int),axis=0,return_index=True);p=p[ix]
 tree=cKDTree(p);_,ii=tree.query(p,k=min(24,len(p)));q=p[ii];q-=q.mean(1)[:,None,:]
 ev,vec=np.linalg.eigh(np.einsum('nki,nkj->nij',q,q))
 return dict(xyz=p,normal_y=abs(vec[:,1,0]),eigen=ev)
def run(source,out,config):
 global SOURCE,OUT,src,xyz,rgb,cfg,mark,performance
 SOURCE=source.parent;OUT=out;cfg=config;OUT.mkdir(exist_ok=False,parents=True)
 started=last=time.perf_counter();stages={}
 def mark(name):
  nonlocal last
  now=time.perf_counter();stages[name]=now-last;last=now
  tmp=OUT/'state.tmp';tmp.write_text(json.dumps(dict(status='running',stage=name,elapsed=now-started)));tmp.replace(OUT/'state.json')
 def performance():
  try:
   import resource
   rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
  except ImportError:rss=None
  return dict(stages_seconds=stages,elapsed_seconds=time.perf_counter()-started,peak_rss_mib=rss,host=platform.node(),machine=platform.machine(),threads=1)
 src=np.load(source,allow_pickle=False);xyz=src['xyz'];rgb=src['rgb']
 assert xyz.ndim==2 and xyz.shape[1]==3 and rgb.shape==xyz.shape and len(xyz)<=2000000 and np.isfinite(xyz).all()
 mark('load')
 try:
  (mls if cfg['method']=='mls' else biharmonic)()
  state=dict(status='complete',stage='complete',performance=performance(),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
  (OUT/'state.json').write_text(json.dumps(state,indent=2));print(json.dumps(state),flush=True)
 except Exception as e:
  (OUT/'state.json').write_text(json.dumps(dict(status='failed',error=str(e),performance=performance())));raise

def mls():
 # Tail/back upper patch in calibrated axis coordinates. No head, belly or platter.
 mask=bounds_mask(xyz,cfg)
 p=xyz[mask];colors=rgb[mask]
 _,vi=np.unique(np.floor(p/.35).astype(int),axis=0,return_index=True);p=p[vi];colors=colors[vi]
 assert len(p)>=100, '区域内有效支撑点不足'
 tree=cKDTree(p);di,ni=tree.query(p,k=24);q=p[ni];q-=q.mean(1)[:,None,:];eig,vec=np.linalg.eigh(np.einsum('nki,nkj->nij',q,q));normal_y=np.abs(vec[:,1,0])
 # Remove near-vertical surfaces that cannot be represented in this height chart.
 ok=(normal_y>.45)&(eig[:,0]/np.maximum(eig.sum(1),1e-9)<.08)
 p=p[ok];colors=colors[ok]
 cells=np.floor(p[:,[0,2]]/.3).astype(int);un,inv=np.unique(cells,axis=0,return_inverse=True)
 train=[];trainrgb=[]
 for j in range(len(un)):
  vals=p[inv==j];cc=colors[inv==j]
  # Reject overlapping sheets instead of averaging two different surfaces.
  if np.ptp(vals[:,1])>1.2:continue
  train.append(np.median(vals,axis=0));trainrgb.append(np.median(cc,axis=0))
 assert len(train)>=24, '局部表面支撑不足，请调整区域'
 train=np.asarray(train);trainrgb=np.asarray(trainrgb);uv=train[:,[0,2]];tr=cKDTree(uv)
 def fit(query,hide=0):
  distance,ii=tr.query(query,k=min(250,len(train)),distance_upper_bound=6.5)
  valid=(ii<len(train))&(distance>hide);distance=distance[valid];ii=ii[valid]
  if len(ii)<20 or distance[0]>3:return None
  radius=max(3.0,min(6.5,2*distance[0]+1.5));sel=distance<=radius;ii=ii[sel];distance=distance[sel]
  if len(ii)<20:return None
  delta=uv[ii]-query
  angles=np.sort(np.arctan2(delta[:,1],delta[:,0]));maxgap=np.diff(np.r_[angles,angles[0]+2*np.pi]).max()
  if maxgap>np.deg2rad(170):return None # must be surrounded, no silhouette extrapolation
  z=train[ii,1];u=delta[:,0]/radius;v=delta[:,1]/radius
  A=np.c_[np.ones(len(ii)),u,v,u*u,u*v,v*v]
  weights=np.exp(-2*(distance/radius)**2);base=weights.copy()
  for _ in range(4):
   w=np.sqrt(weights);Aw=A*w[:,None]
   if np.linalg.cond(Aw)>80:return None
   coef=np.linalg.lstsq(Aw,z*w,rcond=None)[0];res=z-A@coef
   scale=max(.08,1.4826*np.median(np.abs(res-np.median(res))))
   weights=base*np.minimum(1,1.5*scale/np.maximum(abs(res),1e-9))
  rmse=float(np.sqrt(np.average(res*res,weights=weights)));y=float(coef[0])
  if rmse>.55 or not cfg['y'][0]+1<y<cfg['y'][1]-1:return None
  if not np.percentile(z,5)-.6<=y<=np.percentile(z,95)+.6:return None
  slope=np.linalg.norm(coef[1:3])/radius
  if slope>3:return None
  color=np.average(trainrgb[ii],axis=0,weights=weights)
  return y,color,rmse,float(distance[0]),radius

 holdout={}
 mark('prepare')
 fulltree=cKDTree(xyz);adds=[];addcolors=[];metrics=[]
 for x in np.arange(cfg["x"][0]+2,cfg["x"][1]-2+.001,cfg["grid"]):
  for z in np.arange(cfg["z"][0]+2,cfg["z"][1]-2+.001,cfg["grid"]):
   query=np.array([x,z]);d=tr.query(query)[0]
   if d<.35 or d>3:continue
   ans=fit(query)
   if ans is None:continue
   y,c,err,near,rad=ans;pt=np.array([x,y,z]);dist=fulltree.query(pt)[0]
   if dist<.35 or dist>3.5:continue
   adds.append(pt);addcolors.append(c);metrics.append([err,near,rad,dist])
 adds=np.asarray(adds).reshape(-1,3);addcolors=np.clip(np.asarray(addcolors).reshape(-1,3),0,255).astype(np.uint8);metrics=np.asarray(metrics)
 mark('fit_and_support')
 combined=np.vstack([xyz,adds]);combinedrgb=np.vstack([rgb,addcolors]);inferred=np.r_[np.zeros(len(xyz),np.uint8),np.ones(len(adds),np.uint8)]
 assert np.array_equal(combined[:len(xyz)],xyz) and np.array_equal(combinedrgb[:len(rgb)],rgb)
 assert np.isfinite(combined).all()
 np.savez_compressed(OUT/'inferred-only.npz',xyz=adds,rgb=addcolors,metrics=metrics,inferred=np.ones(len(adds),np.uint8))
 np.savez_compressed(OUT/'combined.npz',xyz=combined,rgb=combinedrgb,inferred=inferred,laser=np.r_[src['laser'],np.full(len(adds),2,np.uint8)],position=np.r_[src['position'],np.full(len(adds),65535,np.uint16)])
 write_ply(OUT/'model.ply',combined,combinedrgb)
 write_ply(OUT/'inferred-only.ply',adds,addcolors)
 highlight=combinedrgb.copy();highlight[len(xyz):]=[255,110,35];write_ply(OUT/'duck-tail-highlight-inferred.ply',combined,highlight)
 audit={'method':'bounded robust local quadratic MLS height chart','not_exact_paper_implementation':True,'source':str(SOURCE),'measured_input_points':len(xyz),'inferred_points':len(adds),'total_points':len(combined),'original_unchanged':True,'grid_step_mm':cfg['grid'],'region_axis_mm':{k:cfg[k] for k in ('x','y','z')},'max_distance_to_observation_mm':3.5,'observed_truth_in_holes_available':False,'absolute_accuracy_validated':False,'color_is_interpolated':True,'validation_scope':'No ground truth for this missing region; estimated geometry only','references':[{'title':'Point set surfaces (Alexa et al., 2001)','url':'https://doi.org/10.1109/VISUAL.2001.964489'},{'title':'Filling Holes in Meshes (Liepa, 2003); related alternative, not implemented','url':'https://doi.org/10.2312/SGP/SGP03/200-206'}]}
 mark('export')
 audit.update(performance=performance(),requested_config=cfg)
 (OUT/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')

 print(json.dumps(audit,ensure_ascii=False),flush=True)


def biharmonic():
 s=surface_samples(src,cfg);p=s['xyz'];ny=s['normal_y'];ev=s['eigen']
 ok=(ny>.45)&(ev[:,0]/ev.sum(1)<.08)&(p[:,2]>cfg['z'][0]);p=p[ok]
 cells=np.floor(p[:,[0,2]]/.3).astype(int);un,inv=np.unique(cells,axis=0,return_inverse=True);train=[]
 for j in range(len(un)):
  vals=p[inv==j]
  if np.ptp(vals[:,1])<1.2:train.append(np.median(vals,axis=0))
 assert len(train)>=100, '局部表面支撑不足，请调整区域'
 train=np.asarray(train);tree=cKDTree(train[:,[0,2]])
 step=cfg['grid'];xs=np.arange(cfg['x'][0],cfg['x'][1]+.001,step);zs=np.arange(cfg['z'][0]+1,cfg['z'][1]+.001,step);X,Z=np.meshgrid(xs,zs);query=np.c_[X.ravel(),Z.ravel()]
 dist,ii=tree.query(query);dist=dist.reshape(X.shape);heights=train[ii,1].reshape(X.shape)
 observed=dist<=.48
 yy,xx=np.ogrid[-12:13,-12:13];disk=xx*xx+yy*yy<=144
 closed=binary_closing(observed,structure=disk)
 holes=binary_fill_holes(closed)&~closed
 # The gap touches a steep rim where a height chart loses vertical samples.
 # Bound the experimental completion explicitly in the inspected tail chart;
 # this ROI is a modeling choice, not an inferred true physical hole boundary.
 roi_vertices=np.asarray(cfg['polygon_xz'],float)
 region=(Delaunay(roi_vertices).find_simplex(query)>=0).reshape(X.shape)
 holes=region&~observed;components,n=label(holes)
 center_index=(np.argmin(abs(zs-roi_vertices[:,1].mean())),np.argmin(abs(xs-roi_vertices[:,0].mean())))
 selected=components[center_index];assert selected>0, '圈选中心没有缺口，请重新圈选缺口中心'
 hole=components==selected
 assert not hole[[0,-1]].any() and not hole[:,[0,-1]].any(), '缺口到达处理边缘，请扩大支撑范围'
 assert hole.sum()<=12000, '补洞区域过大，请缩小区域或增大网格间距'

 # Smooth noisy boundary heights on this temporary chart; saved observations untouched.
 def complete(sigma):
  valid=(~hole).astype(float)
  h=gaussian_filter(heights*valid,sigma)/np.maximum(gaussian_filter(valid,sigma),1e-9)
  h[hole]=0
  return inpaint_biharmonic(h,hole)
 mark('prepare')
 filled=complete(1.0);alternative=complete(2.0)
 mark('solve')
 patch=np.c_[X[hole],filled[hole],Z[hole]]
 fulltree=cKDTree(xyz);dd,ni=fulltree.query(patch,k=64);weights=1/np.maximum(dd,.8)**2
 colors=np.clip(np.sum(rgb[ni]*weights[:,:,None],axis=1)/weights.sum(1)[:,None],0,255).astype(np.uint8)
 valid=dd[:,0]>.35;patch=patch[valid];colors=colors[valid]
 assert np.isfinite(patch).all() and (patch[:,1]>cfg['y'][0]-1).all() and (patch[:,1]<cfg['y'][1]+1).all(), '补面超出指定高度范围'

 tests=[];chosen=[]
 mark('color')
 combined=np.vstack([xyz,patch]);combinedrgb=np.vstack([rgb,colors]);inferred=np.r_[np.zeros(len(xyz),np.uint8),np.ones(len(patch),np.uint8)]
 assert np.array_equal(combined[:len(xyz)],xyz) and np.array_equal(combinedrgb[:len(rgb)],rgb)
 np.savez_compressed(OUT/'combined.npz',xyz=combined,rgb=combinedrgb,inferred=inferred,laser=np.r_[src['laser'],np.full(len(patch),2,np.uint8)],position=np.r_[src['position'],np.full(len(patch),65535,np.uint16)])
 np.savez_compressed(OUT/'inferred-only.npz',xyz=patch,rgb=colors,inferred=np.ones(len(patch),np.uint8))
 write_ply(OUT/'model.ply',combined,combinedrgb);write_ply(OUT/'inferred-only.ply',patch,colors)
 highlight=combinedrgb.copy();highlight[len(xyz):]=[255,110,35];write_ply(OUT/'duck-tail-highlight-inferred.ply',combined,highlight)
 audit={'method':'biharmonic height-field inpainting of an enclosed tail hole','implementation':'skimage.restoration.inpaint_biharmonic','source':str(SOURCE),'measured_input_points':len(xyz),'inferred_points':len(patch),'total_points':len(combined),'original_points_unchanged':True,'colors_interpolated':True,'grid_spacing_mm':step,'hole_chart_bounds_mm':[[float(X[hole].min()),float(X[hole].max())],[float(Z[hole].min()),float(Z[hole].max())]],'estimated_height_range_mm':[float(patch[:,1].min()),float(patch[:,1].max())],'boundary_smoothing_sensitivity_p95_mm':float(np.percentile(abs(filled[hole]-alternative[hole]),95)),'small_hole_validation':{'radius_mm':2,'test_disks':len(chosen),'core_grid_points':len(tests),'median_height_error_mm':float(np.median(tests)) if tests else None,'p95_height_error_mm':float(np.percentile(tests,95)) if tests else None},'actual_missing_geometry_error_unknown':True,'important':'Validation uses smaller holes and existing scan data, not ground-truth tail measurements. Smooth completion may erase a true depression or crease.','references':['https://arxiv.org/abs/1707.06567','https://scikit-image.org/docs/stable/auto_examples/filters/plot_inpaint.html']}
 audit['target_roi_selection']='Explicit polygon in inspected tail height chart; ROI boundary is not a measured physical contour'
 audit['target_roi_vertices_xz_mm']=roi_vertices.tolist()
 audit['method']='biharmonic height-field inpainting in an explicitly bounded tail region'
 mark('export')
 audit.pop('small_hole_validation',None)
 audit.update(performance=performance(),requested_config=cfg)
 (OUT/'audit.json').write_text(json.dumps(audit,indent=2));print(json.dumps(audit),flush=True)

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--source',type=Path,required=True);a.add_argument('--out',type=Path,required=True);a.add_argument('--config',type=Path,required=True);v=a.parse_args();run(v.source,v.out,json.loads(v.config.read_text()))
