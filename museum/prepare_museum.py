"""Make display assets for the two existing scans; never modify source files."""
from pathlib import Path
from source_inputs import required_source
import sys, json, hashlib, shutil
import numpy as np
import trimesh, cv2
H=Path(__file__).parent; P=H/'public/museum'; P.mkdir(exist_ok=True)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def adjacency(f):
    a=np.full((len(f),3),-1,np.int32); edges={}
    for i,face in enumerate(f):
        for j in range(3):
            e=tuple(sorted((int(face[j]),int(face[(j+1)%3]))))
            if e in edges:
                k,l=edges.pop(e); a[i,j]=k; a[k,l]=i
            else: edges[e]=(i,j)
    return a
def thumbnail(v,f,labels,palette,path):
    W=640; im=np.full((640,W,3),(236,240,243),np.uint8)
    az=.3;el=.24;cam=np.array([np.cos(el)*np.sin(az),np.sin(el),np.cos(el)*np.cos(az)])
    right=np.array([np.cos(az),0,-np.sin(az)]);up=np.cross(cam,right)
    vv=v-(v.max(0)+v.min(0))/2
    xy=np.c_[vv@right,-vv@up]; scale=480/max(np.ptp(xy[:,0]),np.ptp(xy[:,1]));xy=xy*scale+[320,320]
    normals=np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]]);normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-8)
    light=np.array([-.4,.7,.6]);light/=np.linalg.norm(light)
    lit=.65+.35*np.maximum(0,normals@light);cols=np.array([[int(c[i:i+2],16) for i in [5,3,1]] for c in palette])
    for j in np.argsort((vv@cam)[f].mean(1)):
        cv2.fillConvexPoly(im,xy[f[j]].astype(np.int32),tuple((cols[labels[j]]*lit[j]).astype(int).tolist()),cv2.LINE_AA)
    cv2.imwrite(str(path),im)
duck=P/'duck';duck.mkdir(exist_ok=True)
for n in ['vertices.bin','faces.bin','face-regions.bin','face-adjacency.bin']:
    shutil.copy2(H/'public/assets'/n,duck/n)
dm=json.loads((H/'assets/model.json').read_text(encoding='utf8')); ds=json.loads((H/'assets/segmentation.json').read_text(encoding='utf8'))
dv=np.fromfile(duck/'vertices.bin','<f4').reshape(-1,3);df=np.fromfile(duck/'faces.bin','<u4').reshape(-1,3)
dp=['#f4e5bd','#f4e5bd','#e88b35','#26312d','#f4e5bd','#f4e5bd','#f4e5bd','#26312d']
doll=P/'doll';doll.mkdir(exist_ok=True)
source=required_source('SCAN3D_DOLL_STL'); before=sha(source)
m=trimesh.load(source,force='mesh',process=True); lo,hi=m.bounds; origin=(lo+hi)/2;origin[1]=lo[1]
az=np.deg2rad(35); front=np.array([np.cos(az),0,np.sin(az)]);right=np.cross([0,1,0],front);R=np.array([right,[0,1,0],front]).T
v=(m.vertices-origin)@R;f=m.faces
v.astype('<f4').tofile(doll/'vertices.bin');f.astype('<u4').tofile(doll/'faces.bin')
c=v[f].mean(1);x,y,z=c.T;labels=np.zeros(len(f),np.uint8)
labels[y>27]=2
labels[(y>28)&(y<51)&(z>7)&((x/17)**2+((y-39)/13)**2<1)]=1
labels[y>52]=3
labels[(x<-15)&(y>17)&(y<33)]=4
labels[(x>15)&(y>17)&(y<33)]=5
labels[y<2.5]=6
labels.tofile(doll/'face-regions.bin');adjacency(f).astype('<i4').tofile(doll/'face-adjacency.bin')
pal=['#e7dfd0']*8
items=[dict(id='duck',name='小鸭',category='无脚鸭子摆件',subtitle='把日常的小小陪伴，留在这里。',regions=ds['regions'],palette=dp,faces=len(df),vertices=len(dv),bounds_mm=np.ptp(dv,axis=0).tolist(),geometry_key=ds['geometry_key'],source_scan=dm['source_scan'],source_stl_sha256=dm['source_stl_sha256'],source_stl='/assets/duck-original-mm.stl',features=['圆润的身体','扁平的嘴部','没有脚的扫描外形'],processing='扫描 STL 展示副本，减至 60,000 面；保留已有补全曲面。',segmentation_note='几何先验与连通生长候选；嘴眼种子沿用此前颜色候选，可手动修正。',transform=dm['transform']),
    dict(id='doll',name='娃娃',category='娃娃摆件',subtitle='每个微小轮廓，都值得被记住。',regions=['衣服','面部候选','头发候选','头饰','左侧装饰','右侧装饰','底面','自定细节'],palette=pal,faces=len(f),vertices=len(v),bounds_mm=np.ptp(v,axis=0).tolist(),geometry_key=hashlib.sha256((doll/'vertices.bin').read_bytes()+(doll/'faces.bin').read_bytes()).hexdigest(),source_scan='scan3d-pc-20261010-032157-5c3bcd',source_stl_sha256=before,source_stl='/museum/doll/original-mm.stl',features=['较大的头部','头饰与垂落的发束','坐姿轮廓'],processing='保留主体，移除 5 个离散部分，按底面平面封底；封底属于推断表面。',segmentation_note='按高度、朝向和表面位置生成的粗分区，不是图像语义识别；面部与头发边界需人工修正。',transform=dict(origin=origin.tolist(),rotation=R.tolist()))]
shutil.copy2(source,doll/'original-mm.stl')
for item in items:
    folder=P/item['id'];item['asset_base']='/museum/'+item['id']+'/';item['thumbnail']=item['asset_base']+'thumbnail.jpg'
    vv=np.fromfile(folder/'vertices.bin','<f4').reshape(-1,3);ff=np.fromfile(folder/'faces.bin','<u4').reshape(-1,3);ll=np.fromfile(folder/'face-regions.bin',np.uint8)
    thumbnail(vv,ff,ll,item['palette'],folder/'thumbnail.jpg')
(P/'catalog.json').write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding='utf8')
assert sha(source)==before
print(json.dumps([{'id':i['id'],'faces':i['faces'],'bounds_mm':i['bounds_mm']} for i in items]))
