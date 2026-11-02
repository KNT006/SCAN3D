"""Unchanged core-v3 peak loop extracted for arbitrary object masks.
No geometric identity assignment; preserves the frozen checkerboard detector.
"""
import cv2
import numpy as np
from scipy.signal import find_peaks
METHOD = {'name': 'valley_bounded_core_centroid_development_v3', 'min_peak_distance_px': 8, 'min_peak_prominence': 18, 'min_signal': 80, 'min_width_px': 2, 'max_width_px': 35, 'saturation_threshold': 250, 'reference_assignment_radius_px': 8, 'reference_ambiguity_margin_px': 2, 'grid_edge_exclusion_mm': 0.5, 'comparison_p95_limit_px': 1.5, 'minimum_reference_coverage': 0.8, 'maximum_valley_fraction_of_weaker_peak': 0.8, 'core_weight_floor_fraction': 0.5, 'identity_source': 'single-laser images, for controlled evaluation only'}

SOURCE_SHA256 = "0307385cfde81917ceaf38ab75595b4e8bc65648915e1c727b44354bb44af934"

def extract(on, off, mask):
    signal=np.maximum(on.astype(np.float32)-off.astype(np.float32),0).max(2)
    smooth=cv2.GaussianBlur(signal,(5,1),0)
    selected={};raw_candidates=[];rejected=dict(saturated=0,width_or_border=0,weak=0)
    for y in np.flatnonzero(mask.any(1)):
        valid=np.flatnonzero(mask[y]);left,right=int(valid[0]),int(valid[-1]);row=smooth[y];base=float(np.median(row[valid]))
        peaks,_=find_peaks(row[left:right+1],distance=METHOD['min_peak_distance_px'],prominence=METHOD['min_peak_prominence'])
        candidates=[]
        peaks=peaks+left
        for peak_index,k in enumerate(peaks):
            peak=float(row[k]-base)
            if peak<18:continue
            lower,upper=left,right
            unresolved=False
            for neighbor_index in (peak_index-1,peak_index+1):
                if not 0<=neighbor_index<len(peaks):continue
                neighbor=int(peaks[neighbor_index])
                a,b=sorted((int(k),neighbor))
                valley=a+int(np.argmin(row[a:b+1]))
                weaker=min(peak,float(row[neighbor]-base))
                if row[valley]-base>METHOD['maximum_valley_fraction_of_weaker_peak']*weaker:
                    unresolved=True;break
                if neighbor<k:lower=valley+1
                else:upper=valley-1
            if unresolved or lower>k or upper<k:continue
            lo=hi=int(k);threshold=base+max(6,.2*peak)
            while lo>lower and row[lo-1]>threshold:lo-=1
            while hi<upper and row[hi+1]>threshold:hi+=1
            if lo==left or hi==right or not METHOD['min_width_px']<=hi-lo+1<=METHOD['max_width_px']:
                rejected['width_or_border']+=1;continue
            if on[y,lo:hi+1].max()>=METHOD['saturation_threshold']:
                rejected['saturated']+=1;continue
            if signal[y,max(0,k-3):k+4].max()<METHOD['min_signal']:
                rejected['weak']+=1;continue
            # Subtract the half-height floor before weighting, reducing
            # sensitivity to asymmetric light in the low-intensity wings.
            weights=np.maximum(row[lo:hi+1]-base-METHOD['core_weight_floor_fraction']*peak,0)
            if weights.sum()<=0:continue
            x=float(np.average(np.arange(lo,hi+1),weights=weights))
            candidates.append((x,peak,lo,hi))
        chosen=[]
        for item in sorted(candidates,key=lambda c:-c[1]):
            if all(abs(item[0]-q[0])>=METHOD['min_peak_distance_px'] and (item[3]<q[2] or q[3]<item[2]) for q in chosen):chosen.append(item)
            if len(chosen)==2:break
        xs=sorted(q[0] for q in chosen);selected[int(y)]=xs
        raw_candidates.extend([[x,int(y)] for x in xs])
    return selected, raw_candidates, rejected
