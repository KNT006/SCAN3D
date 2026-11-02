"""Offline integration check. Requires the separately archived cat scan, not hardware.

python test_replay_sync.py --archive <cat-ground-first-20261014> --output <report-dir>
"""
import argparse,json,sys,tempfile,shutil,hashlib,time
from pathlib import Path
import numpy as np
BASE=Path(__file__).resolve().parents[1]/'rootfs/opt/afc03-scanner'
sys.path[:0]=[str(BASE/'scan3d'),str(BASE/'fpga')]
import replay
from rk_candidate_policy import select_candidates
from pointcloud_adapter import PointCloudAdapter
from dual_identity import geometry_candidates
from row_results import ProtocolError


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--archive',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--all',action='store_true');a=parser.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    adapter=PointCloudAdapter(a.archive/'source/bundle',geometry_candidates)
    adapter.turntable_filter=dict(adapter.turntable_filter,min_axis_y_mm=-74.8)
    results=[];start=time.monotonic()
    for index,laser in [(0,'B'),(2544,'A'),(583,'B'),(901,'A'),(530,'B'),(1696,'B')]:
        name=f'{index:04d}-{laser}'
        with tempfile.TemporaryDirectory() as temp:
            temp=Path(temp);source=temp/'job';pos=source/f'position-{index:03d}';target=pos/laser
            shutil.copytree(a.archive/'source'/f'position-{index:03d}'/laser,target)
            for role in (laser,'OFF','COLOR'):
                image=a.archive/'output/images'/f'{index:04d}-{role}.png'
                if image.is_file():
                    (pos/role).mkdir(exist_ok=True);shutil.copy2(image,pos/role/'same-frame.png')
            before={p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
            out=a.output/name;out.mkdir(exist_ok=True)
            request=dict(run='job',index=index,laser=laser,mode='current_scan')
            (out/'request.json').write_text(json.dumps(request))
            result=replay.run(out,source,adapter)
            with np.load(a.archive/'output/near20-v1/frames'/name/'points.npz') as reference:
                assert np.array_equal(result['steps'][-1]['uv'],reference['uv']),name
                assert np.array_equal(result['xyz'],reference['axis_frame_mm']),name
            assert result['report']['long_track_deleted']==0
            assert not result['report']['multipeak_enabled']
            rows=json.loads((out/'row-audit.json').read_text(encoding='utf-8'))
            records=[r for d in rows.values() for r in d['records']]
            assert sum(r['retained'] for r in records)==result['final_count']
            assert all(not r['long_track_suspect'] or r['retained'] for r in records)
            for s in result['steps']:
                assert len(s['uv'])==s['count']
            after={p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
            assert before==after,'Replay modified the archive'
            # Missing ALL images still uses verified candidates and local color statistics.
            for p in pos.rglob('same-frame.png'):p.unlink()
            fallback=temp/'fallback';fallback.mkdir();(fallback/'request.json').write_text(json.dumps(request))
            missing=replay.run(fallback,source,adapter)
            assert missing['steps'][-1]['uv']==result['steps'][-1]['uv']
            assert not missing['row_profiles_available'] and missing['color_source']=='archived_candidate_local_RGB'
            # Reject mismatched identity, truncated payload and missing RGB evidence.
            header=target/'hardware-frame.json';original=header.read_bytes();bad=json.loads(original);bad['source_frame_id']+=1;header.write_text(json.dumps(bad))
            try:replay.run(fallback,source,adapter);raise AssertionError('Accepted mismatched identity')
            except ProtocolError:pass
            header.write_bytes(original)
            binary=target/'records.bin';original=binary.read_bytes();binary.write_bytes(original[:-1])
            try:replay.run(fallback,source,adapter);raise AssertionError('Accepted truncated binary')
            except ProtocolError:pass
            binary.write_bytes(original)
            (target/'strategy-candidates.json').unlink()
            try:replay.run(fallback,source,adapter);raise AssertionError('Accepted missing RGB')
            except ProtocolError:pass
            results.append(dict(frame=name,points=result['final_count'],suspects=result['report']['long_track_suspects'],image_curves=result['row_profiles_available'],seconds=result['seconds']))
            print('Replay OK',name,flush=True)
    count=0
    if a.all:
        for p in sorted((a.archive/'source').glob('position-*/[AB]/frame.json')):
            index=int(p.parent.parent.name.split('-')[1]);name=f'{index:04d}-{p.parent.name}'
            raw=json.loads((p.parent/'strategy-candidates.json').read_text(encoding='utf-8'));header=json.loads(p.read_text());trace={}
            arrays,report,records=select_candidates(raw,header,adapter,trace=trace)
            with np.load(a.archive/'output/near20-v1/frames'/name/'points.npz') as ref:
                for key in ('uv','axis_frame_mm','signal','threshold','adaptive_origin'):assert np.array_equal(arrays[key],ref[key]),(name,key)
            assert len(trace['final'])==len(arrays['uv']) and report['long_track_deleted']==0
            count+=1
            if count%500==0:print('Parity',count,flush=True)
    # Empty candidate list is a valid empty result, not an indexing failure.
    empty,report,_=select_candidates([],header if a.all else json.loads((a.archive/'source/position-000/B/frame.json').read_text()),adapter,trace={})
    assert empty['uv'].shape==(0,2) and report['retained_points']==0
    summary=dict(passed=True,frames=results,full_archive_frames=count,seconds=time.monotonic()-start,checks=['golden near20 exact UV/XYZ','long track advisory preserved','missing images fallback','identity/truncation/no-color rejection','archives unchanged','empty candidates'])
    (a.output/'validation.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
