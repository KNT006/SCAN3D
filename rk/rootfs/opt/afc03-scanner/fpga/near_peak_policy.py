"""PC-only close-peak competition. No absolute weak-brightness or width veto."""
import numpy as np
SETTINGS=dict(distance_strictly_below_px=20,weak_strong_ratio_max=.6,neighbor_radius_rows=4,min_support_rows=5,neighbor_dx_intercept=2,neighbor_dx_per_row=2,fit_median_residual_max_px=2,strong_prediction_error_max_px=3,full_branch_tracking=False)
def decisions(records):
 rows={}
 for r in records:
  if r['new_kept']:rows.setdefault(r['y'],[]).append(r)
 anchors={y:max(rs,key=lambda r:r['signalmax']) for y,rs in rows.items()}
 rejected=set();details={}
 for y,rs in rows.items():
  if len(rs)!=2:continue
  a=anchors[y];b=next(r for r in rs if r is not a)
  gap=abs(a['x']-b['x']);ratio=b['signalmax']/max(a['signalmax'],1)
  # Existing retained row maxima are anchors. No absolute 80/100 threshold.
  support=[(yy,anchors[yy]) for yy in range(y-4,y+5) if yy!=y and yy in anchors and abs(anchors[yy]['x']-a['x'])<=2+2*abs(yy-y)]
  error=residual=None
  if len(support)>=5:
   dy=np.array([yy-y for yy,q in support]);xx=np.array([q['x'] for yy,q in support]);coef=np.polyfit(dy,xx,1)
   error=float(abs(coef[1]-a['x']));residual=float(np.median(abs(np.polyval(coef,dy)-xx)))
  stable=len(support)>=5 and residual<=2 and error<=3
  reason='far_pair'
  if gap<20:
   if ratio>.6:reason='ambiguous_preserved'
   elif not stable:reason='unstable_anchor_preserved'
   else:reason='close_weak_rejected';rejected.add(b['_id'])
  details[b['_id']]=dict(primary_x=a['x'],primary_signal=a['signalmax'],ratio=ratio,gap=gap,anchor_rows=len(support),fit_residual=residual,primary_error=error,stable=bool(stable),decision=reason)
 return rejected,details
