"""Additive row-local rescue after unchanged stripe extraction and geometry.

Only original geometry-valid single rows are anchors. Recovered points never
feed back into extraction, continuity, or another row's rescue decision.
"""
import numpy as np

SETTINGS = dict(version='brightness-frozen-single-v1', strong_min=80,
                weak_exclusive_max=80, ratio_min=3, neighbor_rows=4,
                min_support=3, max_dx_intercept=2, max_dx_per_row=3)

def select_centers(uv, signal, geometry_valid):
    uv=np.asarray(uv,float).reshape(-1,2)
    signal=np.asarray(signal,float)
    valid=np.asarray(geometry_valid,bool)
    if signal.shape!=(len(uv),) or valid.shape!=(len(uv),):
        raise ValueError('Unmatched candidate arrays')
    if not np.isfinite(uv).all() or not np.isfinite(signal).all():
        raise ValueError('Nonfinite candidates')
    if not np.equal(uv[:,1],np.floor(uv[:,1])).all():
        raise ValueError('Rows must be integral')
    rows={}
    for j,(_,y) in enumerate(uv):rows.setdefault(int(y),[]).append(j)
    base=np.array([j for j in range(len(uv)) if valid[j] and len(rows[int(uv[j,1])])==1],int)
    anchors={int(uv[j,1]):float(uv[j,0]) for j in base}
    recovered=[];decisions=[]
    for y,js in rows.items():
        if len(js)!=2:continue
        strong,weak=sorted(js,key=lambda j:signal[j],reverse=True)
        a,b=float(signal[strong]),float(signal[weak])
        rec=dict(row=y,strong_index=int(strong),weak_index=int(weak),strong=a,weak=b,
                 x=float(uv[strong,0]),support_rows=[],accepted=False)
        if not(a>=80 and b<80 and a>=3*b):rec['reason']='brightness_not_decisive'
        elif not valid[strong]:rec['reason']='geometry_invalid'
        else:
            support=[y+dy for dy in range(-4,5) if dy and y+dy in anchors
                     and abs(anchors[y+dy]-uv[strong,0])<=2+3*abs(dy)]
            rec['support_rows']=support
            if len(support)>=3:
                recovered.append(strong);rec.update(accepted=True,reason='brightness_and_frozen_single_support')
            else:rec['reason']='insufficient_frozen_single_support'
        decisions.append(rec)
    return dict(base_indices=base,recovered_indices=np.array(recovered,int),decisions=decisions)
