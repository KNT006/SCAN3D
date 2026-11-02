"""Copy a deterministic, read-only ABI6 archive sample to a NEW external folder.

Never talks to devices or changes archives. PNG conversion is lossless; records
are decoded for coordinates/metadata, but archived CRC integrity is not claimed.
"""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
import cv2

FPGA=Path(__file__).resolve().parents[2]/'rk/rootfs/opt/afc03-scanner/fpga'
sys.path.insert(0,str(FPGA))
from row_results import Center,CandidateExtra,RowDone,decode_record,ADAPTIVE_ALGORITHM


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def image_path(directory):
    for name in ('same-frame.ppm','same-frame.png'):
        path=directory/name
        if path.is_file():return path
    return None


def spread(items):
    """Endpoints then recursively spaced midpoints; deterministic without RNG."""
    if not items:return []
    result=[items[0]]
    if len(items)==1:return result
    result.append(items[-1]);queue=[(1,len(items)-1)]
    while queue:
        lo,hi=queue.pop(0)
        if lo>=hi:continue
        mid=(lo+hi)//2;result.append(items[mid])
        queue.extend(((lo,mid),(mid+1,hi)))
    return result


def collect(jobs,output,limit):
    jobs=Path(jobs).resolve();output=Path(output).resolve()
    if not jobs.is_dir():raise ValueError('jobs directory does not exist')
    if output==jobs or jobs in output.parents:raise ValueError('output must be outside jobs archive')
    if output.exists():raise ValueError('output exists; choose a new directory')
    if not 1<=limit<=200:raise ValueError('limit must be 1..200')
    groups=[];skipped=[]
    runs=sorted(p for p in jobs.iterdir() if p.is_dir() and (p/'status.json').is_file())
    for run in runs:
        try:state=json.loads((run/'status.json').read_text(encoding='utf8'))
        except (OSError,ValueError):continue
        if state.get('status') in ('running','starting','stopping'):
            skipped.append(dict(run=run.name,reason='active archive status'));continue
        found=[]
        for position in sorted(run.glob('position-*')):
            if not position.is_dir():continue
            off=image_path(position/'OFF')
            if off is None:continue
            for laser in ('A','B'):
                folder=position/laser;on=image_path(folder)
                if on and (folder/'records.bin').is_file() and (folder/'hardware-frame.json').is_file():
                    found.append((run,position,laser,off,on))
        if found:groups.append(spread(found))
    selected=[]
    while groups and len(selected)<limit:
        for group in groups:
            if group:selected.append(group.pop(0))
            if len(selected)>=limit:break
        groups=[g for g in groups if g]
    output.mkdir(parents=True)
    manifest=dict(schema=1,source_jobs=str(jobs),selection='sorted runs round-robin; spaced positions and laser frames',requested_limit=limit,samples=[],skipped=skipped,crc_verified=False)
    for run,position,laser,off,on in selected:
        folder=position/laser;header_path=folder/'hardware-frame.json';records_path=folder/'records.bin'
        name=f'{run.name}-{position.name}-{laser}'
        try:
            paths=[off,on,header_path,records_path]
            before={str(p):sha(p) for p in paths}
            header=json.loads(header_path.read_text(encoding='utf8'))
            if header.get('algorithm')!=ADAPTIVE_ALGORITHM:raise ValueError('not ABI6 spatial candidates')
            if header.get('laser_id')!=laser:raise ValueError('laser/header mismatch')
            if header.get('complete') is not True or header.get('error',0)!=0:raise ValueError('incomplete/error hardware frame')
            blob=records_path.read_bytes()
            if not blob or len(blob)%16:raise ValueError('invalid record length')
            decoded=[decode_record(blob[i:i+16]) for i in range(0,len(blob),16)]
            centers=[r for r in decoded if isinstance(r,Center)]
            if any(r.den<=0 for r in centers):raise ValueError('nonpositive candidate denominator')
            if any(r.error for r in decoded if isinstance(r,RowDone)):raise ValueError('row error')
            extras={(r.row,r.index):r for r in decoded if isinstance(r,CandidateExtra)}
            if len({(r.row,r.index) for r in centers})!=len(centers) or len(extras)!=len(centers) or any((r.row,r.index) not in extras for r in centers):raise ValueError('missing/duplicate candidate metadata')
            exact=[[r.row,r.num,r.den,r.peak32,r.lo,r.hi,extras[(r.row,r.index)].peak_x,extras[(r.row,r.index)].strength] for r in centers]
            images=[cv2.imread(str(p),cv2.IMREAD_COLOR) for p in (off,on)]
            if any(im is None or im.shape!=(1080,1920,3) for im in images):raise ValueError('image missing or not native 1920x1080')
            if before!={str(p):sha(p) for p in paths}:raise ValueError('source changed while reading')
            dest=output/name;dest.mkdir()
            for im,label in zip(images,('OFF',laser)):
                if not cv2.imwrite(str(dest/(label+'.png')),im):raise OSError('PNG write failed')
            shutil.copy2(header_path,dest/'hardware-frame.json');shutil.copy2(records_path,dest/'records.bin')
            if sha(dest/'hardware-frame.json')!=before[str(header_path)] or sha(dest/'records.bin')!=before[str(records_path)]:raise ValueError('archive changed during copy')
            uv=[[r.num/r.den,r.row] for r in centers]
            data=dict(request=dict(run=run.name,index=int(position.name.split('-')[-1]),laser=laser),roi=header['geometry']['roi_xyxy'],steps=[dict(key='validated',count=len(uv),uv=uv)],expected_records=exact,hardware_header=header,provenance=dict(source_hashes=before,records_sha256=before[str(records_path)],crc_verified=False,images_native=True,conversion='lossless PNG; no resizing'))
            (dest/'data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
            manifest['samples'].append(dict(sample=name,candidates=len(centers),source_hashes=before))
        except (ValueError,OSError,KeyError,TypeError) as e:
            manifest['skipped'].append(dict(sample=name,reason=str(e)))
        (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    if not selected:(output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    return manifest


def main():
    p=argparse.ArgumentParser();p.add_argument('--jobs',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--limit',type=int,default=32)
    a=p.parse_args();m=collect(a.jobs,a.output,a.limit)
    print(json.dumps(dict(collected=len(m['samples']),skipped=len(m['skipped']),output=str(a.output)),ensure_ascii=False))

if __name__=='__main__':main()
