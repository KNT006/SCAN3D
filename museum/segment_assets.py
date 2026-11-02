"""Create deterministic, editable mesh-region candidates; never write source STL/cloud."""
from pathlib import Path
from collections import deque
import numpy as np
import json, hashlib, shutil
P=Path(__file__).parent; A=P/'assets'
v=np.fromfile(A/'vertices.bin','<f4').reshape(-1,3)
f=np.fromfile(A/'faces.bin','<u4').reshape(-1,3)
c=v[f].mean(1); x,y,z=c.T
adj=np.full((len(f),3),-1,np.int32); edges={}
for i,face in enumerate(f):
    for j in range(3):
        edge=tuple(sorted((int(face[j]),int(face[(j+1)%3]))))
        if edge in edges:
            oi,oj=edges.pop(edge);adj[i,j]=oi;adj[oi,oj]=i
        else:edges[edge]=(i,j)
labels=np.zeros(len(f),np.uint8)
meta=json.loads((A/'model.json').read_text(encoding='utf8'))
def region(index,mask,seed):
    candidates=np.flatnonzero(mask)
    if not len(candidates):return
    first=int(candidates[np.argmin(np.linalg.norm(c[candidates]-seed,axis=1))]); seen={first}; queue=deque([first])
    while queue:
        i=queue.popleft(); labels[i]=index
        for j in adj[i]:
            if j>=0 and j not in seen and mask[j]:seen.add(int(j));queue.append(int(j))
def ellipsoid(center,r):return (((c-np.asarray(center))/np.asarray(r))**2).sum(1)<1
# Anatomical priors + connected growth, not trained semantic segmentation.
region(1,(y>22)&(z>-8),[0,38,10])
region(6,(z<-20)&(y>13),[0,23,-27])
region(4,(x<-18)&(y>8)&(y<20)&(abs(z)<17),[-24,14,0])
region(5,(x>18)&(y>8)&(y<20)&(abs(z)<17),[24,14,0])
region(2,ellipsoid([0,28.8,26.5],[9.2,3.6,5.0])&(z>23),[0,29,29])
for index,key in [(3,'eye_left'),(7,'eye_right')]:
    seed=meta['parts'][key]['point'];region(index,ellipsoid(seed,[1.65,1.85,1.5]),seed)
labels.tofile(A/'face-regions.bin');adj.astype('<i4').tofile(A/'face-adjacency.bin')
info={'version':1,'method':'anatomical geometry priors + seeded connected surface growth','eye_seeds':'previous measured dark-color candidates; editable, not semantic ground truth','regions':['身体','头部','嘴部','左眼','左翼','右翼','尾部','右眼'],'face_counts':np.bincount(labels,minlength=8).tolist(),'geometry_key':hashlib.sha256((A/'vertices.bin').read_bytes()+(A/'faces.bin').read_bytes()).hexdigest(),'note':'候选分区，非学习模型。嘴眼定位沿用既有颜色候选；表面几何和连通性生成面标签，用户可用表面画笔修正。'}
(A/'segmentation.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf8')
for name in ['face-regions.bin','face-adjacency.bin','segmentation.json']:shutil.copy2(A/name,P/'public/assets'/name)
print(json.dumps(info,ensure_ascii=True))
