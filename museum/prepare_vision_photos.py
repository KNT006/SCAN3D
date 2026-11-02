"""Create cropped RGB evidence copies; never modify scan photos or mesh."""
import json, hashlib
from pathlib import Path
import cv2
import numpy as np
from image_colors import ROOT, projection, view_transform

def main():
    manifest={}
    catalog=json.loads((ROOT/'public/museum/catalog.json').read_text(encoding='utf8'))
    tiles=[]
    for item in catalog:
        ident=item['id']; folder=ROOT/'public/museum'/ident
        report=json.loads((folder/'rgb-segmentation/report.json').read_text(encoding='utf8'))
        evidence=report['source']['photo_evidence']
        cam=json.loads((Path(evidence['archive'])/'bundle/camera.json').read_text())
        k=np.array(cam['camera_matrix']); d=np.array(cam['distortion_coefficients'])
        vertices=np.fromfile(folder/'vertices.bin','<f4').reshape(-1,3)
        world=vertices@np.array(item['transform']['rotation']).T+np.array(item['transform']['origin'])
        out=folder/'vision'; out.mkdir(exist_ok=True)
        images=[]
        for index in [0,12,24,36]:
            view=evidence['views'][index]; source=Path(view['image'])
            tr=view_transform(source.parent.parent,k,d)
            if tr is None:raise ValueError('Missing calibrated transform')
            r,t,_=tr; uv=projection(world@r+t,k,d)
            im=cv2.rotate(cv2.imread(str(source)),cv2.ROTATE_90_CLOCKWISE)
            h,w=im.shape[:2]; lo=uv.min(0); hi=uv.max(0); pad=(hi-lo)*.10+8
            x0,y0=np.maximum(0,np.floor(lo-pad)).astype(int)
            x1,y1=np.minimum([w,h],np.ceil(hi+pad)).astype(int)
            crop=im[y0:y1,x0:x1]
            if not crop.size:raise ValueError('Empty crop')
            scale=min(1,1024/max(crop.shape[:2])); crop=cv2.resize(crop,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA)
            name=f'view-{index:02d}.jpg'; cv2.imwrite(str(out/name),crop,[cv2.IMWRITE_JPEG_QUALITY,92])
            images.append({'url':f'/museum/{ident}/vision/{name}','sha256':hashlib.sha256((out/name).read_bytes()).hexdigest(),'source_sha256':view['image_sha256'],'position':view['position'],'crop_xyxy':[int(x0),int(y0),int(x1),int(y1)]})
            tile=np.full((240,240,3),245,np.uint8); s=min(220/crop.shape[0],220/crop.shape[1]); thumb=cv2.resize(crop,None,fx=s,fy=s)
            tile[10:10+thumb.shape[0],10:10+thumb.shape[1]]=thumb; cv2.putText(tile,ident+' '+str(index),(8,235),cv2.FONT_HERSHEY_SIMPLEX,.4,(40,40,40),1); tiles.append(tile)
        manifest[ident]={'geometry_key':item['geometry_key'],'images':images}
        print(ident, len(images),'RGB crops')
    (ROOT/'public/museum/vision-sources.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    cv2.imwrite(str(ROOT/'assets/vision-inputs.jpg'),np.vstack([np.hstack(tiles[i:i+4]) for i in range(0,len(tiles),4)]))

if __name__=='__main__':main()
