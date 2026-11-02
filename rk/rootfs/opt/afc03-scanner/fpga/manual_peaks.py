"""Restrict computation to a padded ROI; preserve raw images and detector semantics."""
import numpy as np
from manual_peaks_reference import extract as reference_extract, METHOD, SOURCE_SHA256
def extract(on,off,mask):
    rows=np.flatnonzero(mask.any(1));cols=np.flatnonzero(mask.any(0))
    if not len(rows): return reference_extract(on,off,mask)
    y0,y1=int(rows[0]),int(rows[-1])+1
    x0,x1=max(0,int(cols[0])-4),min(mask.shape[1],int(cols[-1])+5)
    selected,candidates,rejected=reference_extract(on[y0:y1,x0:x1],off[y0:y1,x0:x1],mask[y0:y1,x0:x1])
    return ({y+y0:[x+x0 for x in xs] for y,xs in selected.items()},[[x+x0,y+y0] for x,y in candidates],rejected)
