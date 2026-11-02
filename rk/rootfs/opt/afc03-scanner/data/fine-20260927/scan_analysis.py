"""Shared stripe extraction for live quality checks and offline reconstruction."""
import cv2
import numpy as np

def rotated(raw):
    assert raw is not None and raw.shape==(1080,1920,3)
    return cv2.rotate(raw,cv2.ROTATE_90_CLOCKWISE)

def stripe(image, background):
    signal=cv2.subtract(image,background).max(2)
    points=[];widths=[];rejected={'weak':0,'width':0,'saturated':0}
    for y in range(335,860):
        row=signal[y,120:950].astype(float);k=int(row.argmax());peak=row[k]
        if peak<18:rejected['weak']+=1;continue
        lo=hi=k;threshold=max(10,peak*.45)
        while lo>0 and row[lo-1]>=threshold:lo-=1
        while hi+1<len(row) and row[hi+1]>=threshold:hi+=1
        if not 2<=hi-lo+1<=35:rejected['width']+=1;continue
        if image[y,120+lo:121+hi].max()>=250:rejected['saturated']+=1;continue
        weights=row[lo:hi+1]
        points.append([120+np.dot(np.arange(lo,hi+1),weights)/weights.sum(),y])
        widths.append(hi-lo+1)
    return np.array(points).reshape(-1,2),np.array(widths),rejected

def repeat_error(uv, other):
    mapping={int(y):x for x,y in other}
    delta=np.array([abs(x-mapping[int(y)]) for x,y in uv if int(y) in mapping])
    if not len(delta):return {'matched':0,'median':None,'p95':None}
    return {'matched':len(delta),'median':float(np.median(delta)),'p95':float(np.percentile(delta,95))}
