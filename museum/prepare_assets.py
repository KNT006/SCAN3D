from pathlib import Path
from source_inputs import required_source
import sys,json,hashlib,shutil
import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
import trimesh,cv2
H=Path(__file__).parent; A=H/'assets';A.mkdir(exist_ok=True)
S=required_source('SCAN3D_SAMPLE_ROOT', directory=True)
cloud=S/'duck-no-turntable/combined.npz'; stl=S/'duck-confidence-stl/duck-confidence-mm.stl'
p=np.load(cloud); valid=p['inferred']==0; xyz=p['xyz'][valid]; rgb=p['rgb'][valid].astype(float)
mesh=trimesh.load(stl,force='mesh',process=True)
low,high=mesh.bounds; height=high[1]-low[1]; center=(low+high)/2
warm=(rgb[:,0]>rgb[:,1]*1.25)&(rgb[:,1]>rgb[:,2]*1.15)&(rgb[:,0]>70)&(xyz[:,1]>low[1]+height*.48)&(xyz[:,1]<low[1]+height*.85)
mouth0=np.median(xyz[warm],axis=0); front=mouth0-center;front[1]=0;front/=np.linalg.norm(front)
right=np.cross([0,1,0],front);R=np.array([right,[0,1,0],front]).T
origin=np.array([center[0],low[1],center[2]])
def trans(a):return (a-origin)@R
q=trans(xyz); m=trans(mouth0); v=trans(mesh.vertices)
print('mouth',m,'bounds',v.min(0),v.max(0),flush=True)
headmask=(q[:,1]>height*.58)&(q[:,2]>m[2]-12)&(q[:,1]>m[1]+2)
brightness=rgb.max(1)
dark=headmask&(brightness<95)&(np.abs(q[:,0])>2)&(np.abs(q[:,0])<17)
def cluster(a):
    if len(a)==0:return []
    _,i=np.unique(np.floor(a/.45).astype(int),axis=0,return_index=True);a=a[i]
    pairs=cKDTree(a).query_pairs(1.1,output_type='ndarray')
    g=coo_matrix((np.ones(len(pairs)),(pairs[:,0],pairs[:,1])),shape=(len(a),len(a)))
    n,labels=connected_components(g,directed=False)
    return [z for k in range(n) if len(z:=a[labels==k])>=4]
parts={}
for sign,name in [(-1,'eye_left'),(1,'eye_right')]:
    clusters=cluster(q[dark & (q[:,0]*sign>0)])
    clusters.sort(key=lambda a:len(a),reverse=True)
    print(name,[(len(a),np.median(a,axis=0).tolist()) for a in clusters[:6]],flush=True)
    point=np.median(clusters[0],axis=0) if clusters else np.array([sign*7,m[1]+7,m[2]-4])
    parts[name]={'point':point.tolist(),'radius':3.2,'method':'深色点聚类＋头部高度＋双侧约束' if clusters else '几何候选，需手动确认','evidence_points':len(clusters[0]) if clusters else 0,'status':'颜色候选' if clusters else '待校准'}
parts['mouth']={'point':m.tolist(),'radius':5.5,'method':'头部中暖色 RGB 点的稳健中位数','evidence_points':int(warm.sum()),'status':'颜色候选'}
for name,target,radius in [('head',[0,height*.76,4],11),('body',[0,height*.3,8],14),('wing_left',[-18,height*.36,0],6),('wing_right',[18,height*.36,0],6),('tail',[0,height*.3,-22],6)]:
    d,i=cKDTree(q).query(target);parts[name]={'point':q[i].tolist(),'radius':radius,'method':'模型朝向＋高度分区＋表面最近点；粗定位','evidence_points':0,'status':'几何估计'}
# A display copy only. The source STL and measured cloud remain unchanged.
import pymeshlab
ms=pymeshlab.MeshSet();ms.add_mesh(pymeshlab.Mesh(vertex_matrix=v,face_matrix=mesh.faces))
ms.meshing_decimation_quadric_edge_collapse(targetfacenum=60000,preservenormal=True,preserveboundary=True)
vv=ms.current_mesh().vertex_matrix();ff=ms.current_mesh().face_matrix()
dist,idx=cKDTree(q).query(vv,k=4)
reliable=dist[:,0]<=1.0
samples=rgb[idx].copy();samples[dist>1.0]=np.nan
import warnings
with warnings.catch_warnings():
    warnings.simplefilter('ignore',RuntimeWarning)
    colors=np.nanmedian(samples,axis=1)
colors[~reliable]=[184,184,175];colors=np.nan_to_num(colors,nan=184).astype(np.uint8)
vv.astype('<f4').tofile(A/'vertices.bin');ff.astype('<u4').tofile(A/'faces.bin');colors.tofile(A/'colors.bin')
_,take=np.unique(np.floor(q/.35).astype(np.int32),axis=0,return_index=True)
q[take].astype('<f4').tofile(A/'points.bin');rgb[take].astype(np.uint8).tofile(A/'point-colors.bin')
shutil.copy2(stl,A/'duck-original-mm.stl')
meta={'source_scan':'fpga-full-20261003-005504','source_cloud':str(cloud),'source_stl':str(stl),'source_cloud_sha256':hashlib.sha256(cloud.read_bytes()).hexdigest(),'source_stl_sha256':hashlib.sha256(stl.read_bytes()).hexdigest(),'source_points':len(p['xyz']),'excluded_inferred':int((~valid).sum()),'display_points':len(take),'vertices':len(vv),'faces':len(ff),'height_mm':float(height),'color_mapping':{'max_distance_mm':1.0,'reliable_fraction':float(reliable.mean()),'nearest_distance_percentiles_mm':np.percentile(dist[:,0],[50,95,99]).tolist(),'fallback_rgb':[184,184,175]},'transform':{'origin':origin.tolist(),'rotation':R.tolist()},'parts':parts,'description':'既有鸭子扫描；坐标已对齐，未重复配准。展示副本减面；颜色取 1mm 内实测点中位数，无可靠近邻区域使用默认材质。'}
(A/'model.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf8')
# Evidence preview, actual projected point colours, not a generated image.
img=np.full((650,760,3),242,np.uint8)
order=np.argsort(q[:,2]);qq=q[order];cc=rgb[order]
for pt,col in zip(qq[::3],cc[::3]):
    x=int(380+pt[0]*10);y=int(580-pt[1]*10)
    if 0<=x<760 and 0<=y<650:cv2.circle(img,(x,y),1,tuple(map(int,col[::-1])),-1)
for name in ['eye_left','eye_right','mouth']:
    pt=parts[name]['point'];xy=(int(380+pt[0]*10),int(580-pt[1]*10));cv2.circle(img,xy,8,(60,150,20),2);cv2.putText(img,name,xy,cv2.FONT_HERSHEY_SIMPLEX,.4,(10,10,10),1)
cv2.imwrite(str(A/'landmarks-check.png'),img)
print(json.dumps({'faces':len(ff),'display_points':len(take),'parts':parts},ensure_ascii=True))
