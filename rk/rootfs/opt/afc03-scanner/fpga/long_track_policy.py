"""PC experiment: two-ended short-fork path competition, independent of brightness.
Single-candidate rows and distant simultaneous paths are not removed.
"""
import numpy as np
SETTINGS=dict(context_each_side_rows=24,min_anchor_rows_each_side=12,
 fork_gap_max_px=32,fork_min_rows=3,fork_max_span_rows=24,
 max_join_missing_rows=2,anchor_fit_median_max_px=2.5,
 velocity_cost_weight=1.,curvature_cost_weight=2.,
 minimum_cost_margin=40.,minimum_branch_deviation_px=8.,
 preserve_single_rows=True,preserve_far_pairs=True)

def best_path(rows):
 """Min-marginals for second-order chain using physical row spacing.
 Cost = sum velocity^2 + 2*sum successive velocity differences^2.
 Forward/backward computations allow a candidate's best forced-path cost.
 """
 yy=np.array([r[0]['y'] for r in rows]);xs=[np.array([r['x'] for r in rr]) for rr in rows]
 n=len(rows);F=[None]*n;P=[None]*n
 v=lambda i,j,k:(xs[i][k]-xs[i-1][j])/(yy[i]-yy[i-1])
 F[1]={(j,k):v(1,j,k)**2 for j in range(len(xs[0])) for k in range(len(xs[1]))}
 for i in range(2,n):
  F[i]={};P[i]={}
  for j in range(len(xs[i-1])):
   for k in range(len(xs[i])):
    vv=v(i,j,k)
    opts=[(val+vv*vv+2*(vv-v(i-1,h,j))**2,h) for (h,jj),val in F[i-1].items() if jj==j]
    cost,h=min(opts);F[i][j,k]=cost;P[i][j,k]=h
 B=[None]*n;B[-1]={jk:0. for jk in F[-1]}
 for i in range(n-2,0,-1):
  B[i]={}
  for h,j in F[i]:
   B[i][h,j]=min(v(i+1,j,k)**2+2*(v(i+1,j,k)-v(i,h,j))**2+B[i+1][j,k] for k in range(len(xs[i+1])))
 pair=min(F[-1],key=F[-1].get);best=F[-1][pair];path=[0]*n;path[-2:]=pair
 for i in range(n-1,1,-1):path[i-2]=P[i][path[i-1],path[i]]
 margins={}
 for i in range(1,n):
  for k,r in enumerate(rows[i]):margins[r['_id']]=float(min(cost+B[i][j,kk] for (j,kk),cost in F[i].items() if kk==k)-best)
 return path,float(best),margins

def decisions(records):
 by={}
 for r in records:
  if r['new_kept']:by.setdefault(r['y'],[]).append(r)
 for rs in by.values():rs.sort(key=lambda r:r['x'])
 seeds=sorted(y for y,rs in by.items() if len(rs)==2 and 8<=abs(rs[0]['x']-rs[1]['x'])<32)
 groups=[]
 for y in seeds:
  if groups and y-groups[-1][-1]<=3:groups[-1].append(y)
  else:groups.append([y])
 reject=set();details={}
 for group in groups:
  lo,hi=group[0],group[-1]
  if len(group)<3 or hi-lo+1>24:continue
  ys=sorted(y for y in by if lo-24<=y<=hi+24)
  # If another distant surface or a gap interrupts the context, do not force one path.
  if any(b-a>3 for a,b in zip(ys,ys[1:])):continue
  if any(len(by[y])>2 or (len(by[y])==2 and abs(by[y][0]['x']-by[y][1]['x'])>=32) for y in ys):continue
  before=[by[y][0] for y in ys if y<lo and len(by[y])==1]
  after=[by[y][0] for y in ys if y>hi and len(by[y])==1]
  if min(len(before),len(after))<12:continue
  # A quadratic check permits genuine smooth turns, unlike a straight-line veto.
  fit=[]
  for anchor in [before,after]:
   xx=np.array([r['x'] for r in anchor]);yy=np.array([r['y']-lo for r in anchor]);co=np.polyfit(yy,xx,2)
   fit.append(float(np.median(abs(np.polyval(co,yy)-xx))))
  if max(fit)>2.5:continue
  rr=[by[y] for y in ys];path,cost,margins=best_path(rr)
  for i,y in enumerate(ys):
   if y not in group:continue
   chosen=rr[i][path[i]]
   for r in rr[i]:
    deviation=abs(r['x']-chosen['x']);margin=margins.get(r['_id'],0)
    removed=deviation>=8 and margin>=40
    f=dict(decision='long_track_rejected' if removed else 'long_track_retained',selected_x=chosen['x'],selected_signal=chosen['signalmax'],deviation=deviation,cost_margin=margin,best_path_cost=cost,window_rows=[ys[0],ys[-1]],fork_rows=[lo,hi],anchor_rows=[len(before),len(after)],anchor_fit_residuals=fit)
    details[r['_id']]=f
    if removed:reject.add(r['_id'])
 return reject,details
