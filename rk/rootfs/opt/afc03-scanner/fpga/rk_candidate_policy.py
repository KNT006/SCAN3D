"""RK candidate-only filter, parity with PC near20-v1; trajectory is advisory."""
import copy,time
import numpy as np
from dual_identity import geometry_candidates
from rk_stripe_strategy import Frame
from rgb_adaptive_strategy import byrow,continuous,supporters
from spatial_filter import radial_mask,supported
from turntable_filter import filter_mask
from secondary_candidate_policy import decisions as secondary_decisions
from near_peak_policy import decisions as near_decisions
from long_track_policy import decisions as long_decisions
VERSION='rk-ground-first-near20-long-advisory-v1'

def finite_geometry(uv,camera,planes,axis,**kwargs):
 _,clouds=geometry_candidates(uv,camera,planes,axis,max_radius_mm=None)
 labels=[set() for _ in uv]
 for label,xyz in clouds.items():
  for i in np.flatnonzero(np.isfinite(xyz).all(1)):labels[i].add(label)
 return labels,clouds

def select_branch(raw,adaptive,trace=None):
 reasons={r['_id']:'RGB/差分阈值或弱峰宽度' for r in raw};chosen=[];eligible_all=[]
 for y,row in byrow(raw).items():
  eligible=[r for r in row if r['signalmax']>=(r['threshold'] if adaptive else 40) and (not adaptive or r['signalmax']>=40 or r['width']<=25)]
  if trace is not None:eligible_all.extend(eligible)
  local=[]
  for r in sorted(eligible,key=lambda r:-r['peak32']):
   reasons[r['_id']]='峰间距/窗口重叠或每行前2候选限制'
  for r in sorted(eligible,key=lambda r:-r['peak32']):
   if all(abs(r['x']-q['x'])>=8 and (r['hi']<q['lo'] or r['lo']>q['hi']) for q in local):local.append(r)
   if len(local)==2:break
  chosen.extend(local)
 first=continuous(chosen)
 narrow=[r for r in first if r['signalmax']>=80 or r['width']<=65]
 final=continuous(narrow)
 for group,reason in [(chosen,'第一次邻行连续性不足'),(first,'弱亮宽峰限制'),(narrow,'第二次邻行连续性不足'),(final,'空间有效邻行支持不足')]:
  for r in group:reasons[r['_id']]=reason
 uv=np.array([[r['x'],r['y']] for r in final],float).reshape(-1,2)
 mask=supported(uv,np.ones(len(uv),bool))
 kept=[r for r,m in zip(final,mask) if m]
 spatial_kept=kept
 if adaptive:
  pool=byrow(final)
  for r in kept:reasons[r['_id']]='自适应弱峰邻行支持不足4行'
  kept=[r for r in kept if r['signalmax']>=40 or len(supporters(r,pool))>=4]
 for r in kept:reasons[r['_id']]='保留'
 if trace is not None:
  trace.update({k:[r['_id'] for r in rows] for k,rows in [('threshold',eligible_all),('top2',chosen),('continuity1',first),('weak_width',narrow),('continuity2',final),('spatial_support',spatial_kept),('retained',kept)]})
  trace['reasons']=reasons
 return kept,reasons,dict(chosen=len(chosen),continuity1=len(first),weak_width=len(narrow),continuity2=len(final),spatial_support=int(mask.sum()),retained=len(kept))


def select_candidates(raw,header,adapter,diagnostics=True,trace=None):
 started=time.perf_counter()
 # Private adapter prevents changing another reconstruction worker's geometry/filter.
 local=copy.copy(adapter);local.geometry_candidates=finite_geometry;local.turntable_filter=None
 raw=[dict(r,_id=j) for j,r in enumerate(raw)]
 uv=np.array([[r['x'],r['y']] for r in raw],float).reshape(-1,2)
 cloud=local.reconstruct(Frame(header,uv));ids=cloud['kept_record_indices'];mapping={int(k):i for i,k in enumerate(ids)}
 ground=adapter.turntable_filter
 above,ground_report=filter_mask(cloud['axis_frame_mm'],ground)
 radial,radii,spatial_report=radial_mask(cloud['axis_frame_mm'],adapter.spatial_filter)
 geom=(cloud['camera_xyz_mm'][:,2]>80)&(cloud['camera_xyz_mm'][:,2]<350)&radial
 spatial=[];stages={}
 for j,r in enumerate(raw):
  i=mapping.get(j)
  r.update(height_mm=float(cloud['axis_frame_mm'][i,1]) if i is not None else None,radius_mm=float(radii[i]) if i is not None else None,new_kept=False)
  if i is None:stages[j]='无有限射线交点'
  elif not above[i]:stages[j]='第一步：转盘高度剔除'
  elif not geom[i]:stages[j]='第二步：几何深度/半径剔除'
  else:spatial.append(r)
 main_trace={} if trace is not None else None;extra_trace={} if trace is not None else None
 main,mreasons,mstat=select_branch(spatial,False,main_trace);extra,ereasons,estat=select_branch(spatial,True,extra_trace)
 occupied={r['y'] for r in main};added=[r for r in extra if r['y'] not in occupied];adaptive={r['_id'] for r in added}
 chosen=sorted(main+added,key=lambda r:r['y']);selected={r['_id'] for r in chosen}
 for r in raw:
  j=r['_id'];r['new_kept']=j in selected
  r['final_reason']=('保留：RGB自适应补充' if j in adaptive else '保留：固定40主支路') if j in selected else stages.get(j,'主支路：'+mreasons.get(j,'')+'；自适应：'+ereasons.get(j,''))
  if j not in selected and r['y'] in occupied and ereasons.get(j)=='保留':r['final_reason']='主支路已占此行：不加入自适应补充候选'
 secondary,secondary_features=secondary_decisions(raw)
 for r in raw:
  if r['_id'] in secondary:r.update(new_kept=False,final_reason='弱宽次候选：稳定主线及重复侧支联合剔除')
 after_secondary=[r['_id'] for r in raw if r['new_kept']] if trace is not None else None
 near,near_features=near_decisions(raw)
 for r in raw:
  if r['_id'] in near:r.update(new_kept=False,final_reason='近峰小于20像素：弱峰不超过60%且强峰轨迹稳定')
 # Diagnostic results MUST NOT participate in selection, support or geometry.
 diag_started=time.perf_counter();suspects,details=long_decisions(raw) if diagnostics else (set(),{})
 for r in raw:
  j=r['_id'];r.update(secondary_features=secondary_features.get(j),near_peak=near_features.get(j),long_track_suspect=j in suspects)
  if j in details:
   r['long_track']=dict(details[j],decision='suspect_only' if j in suspects else 'retained',deletion_enabled=False)
 chosen=[r for r in chosen if r['new_kept']];gi=np.array([mapping[r['_id']] for r in chosen],int)
 if trace is not None:
  trace.update(finite=[int(i) for i in ids],ground=[int(j) for j,m in zip(ids,above) if m],geometry=[r['_id'] for r in spatial],main=main_trace,adaptive=extra_trace,merged=sorted(selected),after_secondary=after_secondary,final=[r['_id'] for r in chosen],suspects=sorted(suspects),adaptive_added=sorted(adaptive))
 arrays={k:cloud[k][gi] for k in ('uv','camera_xyz_mm','camera_aligned_mm','axis_frame_mm')}
 n=len(chosen);arrays.update(scheme2=np.zeros(n,np.uint8),ground_branch=np.zeros(n,np.uint8),
  signal=np.array([r['signalmax'] for r in chosen],float),width=np.array([r['width'] for r in chosen],int),
  saturated=np.array([r.get('saturated',0) for r in chosen],np.uint8),adaptive_origin=np.array([r['_id'] in adaptive for r in chosen],np.uint8),
  threshold=np.array([r['threshold'] if r['_id'] in adaptive else 40 for r in chosen],np.uint8),
  long_track_suspect=np.array([r['_id'] in suspects for r in chosen],np.uint8))
 report=dict(version=VERSION,candidates=len(raw),finite_candidates=len(ids),after_ground=int(above.sum()),after_geometry=len(spatial),
  main_branch=mstat,adaptive_branch=estat,retained_points=n,adaptive_added=int(arrays['adaptive_origin'].sum()),
  secondary_removed=len(secondary),near_peak_removed=len(near),long_track_suspects=len(suspects),long_track_deleted=0,
  long_track_mode='advisory_only',long_track_seconds=time.perf_counter()-diag_started,
  multipeak_enabled=False,ground_branch=dict(enabled=False,added_points=0),spatial_filter=spatial_report,turntable_filter=ground_report,
  pipeline=['validated_fpga_candidates','ground_height','geometry_and_radius','local_rgb_threshold_and_width','continuity','secondary_guard','near20_ratio60','long_track_advisory'],
  seconds=time.perf_counter()-started,inferred_points=0)
 return arrays,report,raw
