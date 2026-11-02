"""Lossless full-frame storage and same-pose RGB sampling."""
import hashlib,json
from pathlib import Path
import cv2,numpy as np

def sample_rgb(image,uv):
    uv=np.asarray(uv,float).reshape(-1,2)
    if not len(uv):return np.empty((0,3),np.uint8)
    x,y=np.floor(uv).astype(int).T;dx,dy=(uv-np.floor(uv)).T
    if not(np.isfinite(uv).all() and (x>=0).all() and (y>=0).all() and
           (x+1<image.shape[1]).all() and (y+1<image.shape[0]).all()):raise ValueError('Colour pixel outside frame')
    out=image[y,x]*(1-dx[:,None])*(1-dy[:,None])+image[y,x+1]*dx[:,None]*(1-dy[:,None])+image[y+1,x]*(1-dx[:,None])*dy[:,None]+image[y+1,x+1]*dx[:,None]*dy[:,None]
    return np.rint(out).clip(0,255).astype(np.uint8)

def compress_position(folder):
    folder=Path(folder).resolve();records=[]
    for source in sorted(folder.glob('*/same-frame.ppm')):
        if source.is_symlink() or folder not in source.resolve().parents:raise ValueError('Unexpected source path')
        target=source.with_suffix('.png')
        if target.exists():raise ValueError('Compressed target already exists')
        original=source.read_bytes();image=cv2.imdecode(np.frombuffer(original,np.uint8),cv2.IMREAD_COLOR)
        if image is None:raise ValueError('Invalid source frame')
        ok,encoded=cv2.imencode('.png',image,[cv2.IMWRITE_PNG_COMPRESSION,1])
        if not ok:raise ValueError('PNG encoding failed')
        target.write_bytes(encoded.tobytes())
        if not np.array_equal(cv2.imread(str(target),cv2.IMREAD_COLOR),image):raise ValueError('PNG pixel readback mismatch')
        records.append(dict(source=source.relative_to(folder).as_posix(),target=target.relative_to(folder).as_posix(),
            original_sha256=hashlib.sha256(original).hexdigest(),png_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            original_bytes=len(original),compressed_bytes=target.stat().st_size,pixels_equal=True))
        # Only this new run's PPM is removed, after exact decoded-pixel readback.
        source.unlink()
    (folder/'lossless-storage.json').write_text(json.dumps(records,indent=2))
    return sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())

def write_ply(path,xyz,rgb):
    xyz=np.asarray(xyz,dtype='<f4');rgb=np.asarray(rgb,dtype='u1')
    if xyz.shape!=rgb.shape or xyz.ndim!=2 or xyz.shape[1]!=3 or not np.isfinite(xyz).all():raise ValueError('Invalid point cloud')
    data=np.empty(len(xyz),dtype=[('x','<f4'),('y','<f4'),('z','<f4'),('r','u1'),('g','u1'),('b','u1')])
    for i,k in enumerate(('x','y','z')):data[k]=xyz[:,i]
    for i,k in enumerate(('r','g','b')):data[k]=rgb[:,i]
    header=('ply\nformat binary_little_endian 1.0\nelement vertex %d\n'%len(xyz)+
        'property float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n').encode()
    Path(path).write_bytes(header+data.tobytes())
