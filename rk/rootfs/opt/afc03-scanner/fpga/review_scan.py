"""Offline review only; preserves the failed closure gate and never controls hardware."""
import argparse,json,zlib,hashlib,time
from pathlib import Path
import numpy as np
from scan_storage import write_ply
from stationary import write

def review(root):
    state=json.loads((root/'status.json').read_text())
    if state['completed_positions']!=801 or state['last_index']!=800 or state['status']=='running':raise ValueError('Acquisition not fully available')
    out=root/'review';out.mkdir(exist_ok=True)
    xyz={k:[] for k in ('A','B')};rgb={k:[] for k in xyz};counts={k:[] for k in xyz};timings={k:[] for k in xyz}
    streams=set();hashes=set();origin=state['initial_motor']['emitted'];frames=0
    for i in range(801):
        p=root/f'position-{i:03d}';report=json.loads((p/'status.json').read_text())
        if not report.get('passed'):raise ValueError('Failed position '+str(i))
        for k in xyz:
            h=json.loads((p/k/'frame.json').read_text());payload=(p/k/'records.bin').read_bytes()
            if not h['complete'] or h['error']!=0 or h['angle']['emitted_after']!=origin+4*i:raise ValueError('Frame/angle invalid')
            if zlib.crc32(payload)!=report['lasers'][k]['payload_crc32']:raise ValueError('Saved CRC mismatch')
            hashes.add(json.dumps(h['calibration'],sort_keys=True));streams.add(h['stream_epoch'])
            with np.load(p/k/'points.npz',allow_pickle=False) as a:
                if len(a['axis_frame_mm'])!=report['lasers'][k]['retained_points']:raise ValueError('Point count mismatch')
                counts[k].append(len(a['axis_frame_mm']));timings[k].append(report['lasers'][k]['extract_and_receive_s'])
                if i<800:xyz[k].append(a['axis_frame_mm']);rgb[k].append(a['rgb'])
            frames+=1
    if len(streams)!=1 or len(hashes)!=1:raise ValueError('Changed camera/calibration identity')
    combined=[];colors=[];labels=[];detail={}
    for label in xyz:
        points=np.concatenate(xyz[label]);color=np.concatenate(rgb[label]);target=out/label;target.mkdir(exist_ok=True)
        np.savez_compressed(target/'points.npz',axis_frame_mm=points,rgb=color)
        write_ply(target/'points.ply',points,color)
        combined.append(points);colors.append(color);labels.append(np.full(len(points),0 if label=='A' else 1,np.uint8))
        detail[label]=dict(points=len(points),points_per_view_min=min(counts[label]),points_per_view_median=float(np.median(counts[label])),
            extract_receive_median_s=float(np.median(timings[label])),extract_receive_p95_s=float(np.percentile(timings[label],95)))
    xyz=np.concatenate(combined);rgb=np.concatenate(colors);labels=np.concatenate(labels)
    np.savez_compressed(out/'combined.npz',xyz=xyz,rgb=rgb,laser=labels)
    write_ply(out/'UNVALIDATED-color.ply',xyz,rgb)
    audit=dict(accepted=False,reason='Original 3-pixel closure gate remains failed',source_frames_checked=frames,
        positions_checked=801,duplicate_360_frame_excluded=True,points=len(xyz),lasers=detail,
        bounds_min_mm=xyz.min(0).tolist(),bounds_max_mm=xyz.max(0).tolist(),
        robust_bounds_mm=np.percentile(xyz,[1,99],axis=0).tolist(),closure=state['closure'],
        elapsed_seconds=state['elapsed_seconds'],capture_retries=state['capture_retries'])
    write(out/'audit.json',audit)
    state['review_ready']=True;state['review_points']=len(xyz);state['review_note']='整圈采集完成；首尾一致性未通过，以下仅供检查。'
    write(root/'status.json',state)
    print(json.dumps(audit,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);review(p.parse_args().root)
