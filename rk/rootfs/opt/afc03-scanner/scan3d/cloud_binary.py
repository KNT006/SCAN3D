"""One-shot, full-resolution result cloud; live incremental API stays separate."""
from pathlib import Path
import json,struct,threading,os
import numpy as np
LOCK=threading.Lock()
MAGIC=0x31443353

def cloud_response(target,info,if_none_match=None):
    """Revalidate the generated full cloud before reusing the browser's bytes."""
    import hashlib
    from fastapi.responses import FileResponse,Response
    stat=target.stat()
    identity=json.dumps([info['source'],stat.st_size,stat.st_mtime_ns],sort_keys=True)
    etag='"'+hashlib.sha256(identity.encode()).hexdigest()+'"'
    headers={'Cache-Control':'private, no-cache','ETag':etag,
             'X-Cloud-Points':str(info['points']),'X-Cloud-Sampling':'none'}
    tags=[tag.strip().removeprefix('W/') for tag in (if_none_match or '').split(',')]
    if etag in tags or '*' in tags:
        return Response(status_code=304,headers=headers)
    return FileResponse(target,media_type='application/octet-stream',headers=headers,stat_result=stat)

def build_cloud(folder,source):
    folder=Path(folder);sources=[Path(p) for p in source] if isinstance(source,list) else [Path(source)]
    target=folder/'result-cloud-v1.bin';meta=folder/'result-cloud-v1.json'
    fingerprint=[dict(source=str(p.relative_to(folder)),size=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns) for p in sources]
    with LOCK:
        try:
            old=json.loads(meta.read_text())
            if old['source']==fingerprint and target.stat().st_size==16+old['points']*15:return target,old
        except (OSError,ValueError,KeyError):pass
        positions=[];colors=[]
        for source in sources:
            with np.load(source,allow_pickle=False) as d:
                positions.append(np.asarray(d['xyz'] if 'xyz' in d.files else d['axis_frame_mm'],dtype='<f4'))
                colors.append(np.asarray(d['rgb'],dtype=np.uint8))
        xyz=positions[0] if len(positions)==1 else np.concatenate(positions)
        rgb=colors[0] if len(colors)==1 else np.concatenate(colors)
        if xyz.ndim!=2 or xyz.shape[1]!=3 or rgb.shape!=xyz.shape or not np.isfinite(xyz).all():
            raise ValueError('Invalid point cloud shape or coordinates')
        count=len(xyz)
        if count>0xffffffff:raise ValueError('Cloud too large')
        tmp=target.with_suffix('.tmp')
        with tmp.open('wb') as f:
            f.write(struct.pack('<4I',MAGIC,1,count,count));f.write(xyz.tobytes());f.write(rgb.tobytes());f.flush();os.fsync(f.fileno())
        tmp.replace(target)
        report=dict(source=fingerprint,points=count,displayed_points=count,sampling='none',bytes=target.stat().st_size)
        tmp=meta.with_suffix('.tmp');tmp.write_text(json.dumps(report));tmp.replace(meta)
        return target,report
