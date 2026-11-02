"""Additive, non-iterative rescue of original two-candidate rows.

No device access. Ground classification comes from calibrated axis coordinates.
Large image separation alone never selects the brighter peak.
"""
import numpy as np
from spatial_filter import DEFAULT,radial_mask,supported

def select_cloud(uv,signal,cloud,ground,selector=None,settings=None):
 """Remove known out-of-volume candidates before counting peaks in a row."""
 uv=np.asarray(uv,float).reshape(-1,2);signal=np.asarray(signal,float)
 gid=np.asarray(cloud['kept_record_indices'],int)
 valid=np.zeros(len(uv),bool);valid[gid]=True
 cfg=cloud.get('spatial_profile',DEFAULT)
 keep,radii,report=radial_mask(cloud['axis_frame_mm'],cfg)
 inside=np.zeros(len(uv),bool);inside[gid]=keep
 radius=np.full(len(uv),np.nan);radius[gid]=radii
 if not cfg['enabled']:
  result=_select_cloud(uv,signal,cloud,ground,selector,settings)
  support=valid.copy()
 else:
  # Invalid triangulation is unknown, never proof that a rival lies outside.
  excluded=valid&~inside
  old_ids=np.flatnonzero(~excluded)
  inverse=np.full(len(uv),-1,int);inverse[old_ids]=np.arange(len(old_ids))
  support=supported(uv,inside,settings)
  cloud_keep=keep&support[gid]
  sub=dict(cloud)
  for key in ('uv','camera_xyz_mm','camera_aligned_mm','axis_frame_mm'):sub[key]=cloud[key][cloud_keep]
  sub['kept_record_indices']=inverse[gid[cloud_keep]]
  result=_select_cloud(uv[old_ids],signal[old_ids],sub,ground,selector,settings)
  for key in ('indices','before_ground_indices'):result[key]=old_ids[result[key]]
  for key in ('base_indices','recovered_indices'):result['selected'][key]=old_ids[result['selected'][key]]
  for decisions in (result['selected']['decisions'],result['branch_decisions']):
   for d in decisions:
    for key in ('index','strong_index','weak_index','rejected_ground_index'):
     if key in d:d[key]=int(old_ids[d[key]])
  result['valid']=valid
 report.update(continuity_rejected=int((inside&~support).sum()),before_multipeak=True,invalid_geometry_points=int((~valid).sum()))
 result.update(spatial_report=report,spatial_valid=inside,spatial_supported=support,radius_mm=radius)
 return result

VERSION='ground-unique-frozen-branch-v1'
SETTINGS=dict(neighbor_rows=4,min_support=3,dx_intercept=2,dx_per_row=3,
              ground_margin_mm=0,large_separation_diagnostic_px=100)

def rescue(uv,valid,above_ground,original_ids,settings=None):
 cfg=dict(SETTINGS)
 if settings is not None:cfg.update({k:settings[k] for k in ("neighbor_rows","min_support","dx_intercept","dx_per_row")})
 uv=np.asarray(uv,float).reshape(-1,2);valid=np.asarray(valid,bool);above=np.asarray(above_ground,bool)
 original=np.asarray(original_ids,int)
 assert valid.shape==above.shape==(len(uv),) and np.isfinite(uv).all()
 assert np.all(uv[:,1]==np.floor(uv[:,1])) and np.all(valid[original]&above[original])
 rows={}
 for i,(_,y) in enumerate(uv):rows.setdefault(int(y),[]).append(i)
 original_set=set(original.tolist());eligible=[];details=[]
 for y,js in rows.items():
  if len(js)!=2:continue
  a,b=js
  if not(valid[a] and valid[b]) or above[a]==above[b]:continue
  j,other=(a,b) if above[a] else (b,a)
  if j in original_set:continue
  eligible.append(j);details.append(dict(row=y,index=j,rejected_ground_index=other,separation_px=float(abs(uv[a,0]-uv[b,0]))))
 # Frozen support pool: original final points plus geometrically unique candidates.
 # Decisions cannot create additional support or cause iterative propagation.
 pool={}
 for j in [*original.tolist(),*eligible]:pool.setdefault(int(uv[j,1]),[]).append(float(uv[j,0]))
 added=[]
 for d in details:
  j=d['index'];x,y=uv[j];supports=[int(y+dy) for dy in range(-cfg["neighbor_rows"],cfg["neighbor_rows"]+1) if dy and any(abs(xx-x)<=cfg["dx_intercept"]+cfg["dx_per_row"]*abs(dy) for xx in pool.get(int(y+dy),[]))]
  d.update(support_rows=supports,accepted=len(supports)>=cfg["min_support"])
  if d['accepted']:added.append(j)
 added=np.asarray(added,int)
 assert not(original_set&set(added.tolist()))
 return dict(added_indices=added,final_indices=np.sort(np.r_[original,added]),decisions=details)


def _select_cloud(uv,signal,cloud,ground,selector=None,settings=None):
 """Add calibrated unique branches to the unchanged legacy final selection.

 Geometry is evaluated without the ground cut. Invalid triangulation is never
 interpreted as background. Support is frozen and each neighboring row votes once.
 """
 from multipeak_policy import select_centers
 from turntable_filter import filter_mask
 uv=np.asarray(uv,float).reshape(-1,2)
 geometry_ids=np.asarray(cloud['kept_record_indices'],int)
 valid=np.zeros(len(uv),bool);valid[geometry_ids]=True
 selected=(selector or select_centers)(uv,signal,valid)
 legacy_ids=np.sort(np.r_[selected['base_indices'],selected['recovered_indices']])
 mapping=np.full(len(uv),-1,int);mapping[geometry_ids]=np.arange(len(geometry_ids))
 above=np.zeros(len(uv),bool);above[geometry_ids]=filter_mask(cloud['axis_frame_mm'],ground)[0]
 _,legacy_ground=filter_mask(cloud['axis_frame_mm'][mapping[legacy_ids]],ground)
 original=legacy_ids[above[legacy_ids]]
 result=rescue(uv,valid,above,original,settings=settings)
 ids=result['final_indices'];gi=mapping[ids]
 arrays={k:cloud[k][gi] for k in ('uv','camera_xyz_mm','camera_aligned_mm','axis_frame_mm')}
 arrays['scheme2']=np.isin(ids,selected['recovered_indices']).astype(np.uint8)
 arrays['ground_branch']=np.isin(ids,result['added_indices']).astype(np.uint8)
 # Include rescued non-ground branches in the input of the final ground stage.
 before_ground=np.sort(np.r_[legacy_ids,result['added_indices']])
 _,ground_report=filter_mask(cloud['axis_frame_mm'][mapping[before_ground]],ground)
 actual_settings=dict(SETTINGS)
 if settings is not None:actual_settings.update({k:settings[k] for k in ('neighbor_rows','min_support','dx_intercept','dx_per_row')})
 report=dict(version=VERSION,settings=actual_settings,enabled=ground is not None,
   original_final_points=len(original),eligible_points=len(result['decisions']),
   added_points=len(result['added_indices']),original_points_removed=0,
   final_points=len(ids),support_rejected=sum(not d['accepted'] for d in result['decisions']),
   cross_angle_gate=False,large_separation_gate=False,legacy_turntable_filter=legacy_ground)
 return dict(arrays=arrays,indices=ids,valid=valid,selected=selected,
   before_ground_indices=before_ground,ground_report=ground_report,
   branch_report=report,branch_decisions=result['decisions'])
