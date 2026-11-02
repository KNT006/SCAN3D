import hashlib
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'rootfs/opt/afc03-scanner/scan3d'))
from live_preview import preview_page


class PreviewTest(unittest.TestCase):
    def test_full_circle_gaps_restart_and_immutable_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            (p/'status.json').write_text(json.dumps(dict(completed_positions=3201,planned_intervals=3200)))
            for i in range(3201):
                d=p/f'position-{i:03d}';d.mkdir()
                (d/'status.json').write_text('{"status":"complete"}')
                for label in ('A','B'):
                    (d/label).mkdir()
                    x=np.zeros((0 if i==15 else 60,3));x[:,0]=i;x[:,1]=np.arange(len(x));x[:,2]=1 if label=='A' else 2
                    c=np.zeros_like(x,dtype=np.uint8);c[:,0]=i%256;c[:,1]=x[:,1]
                    np.savez_compressed(d/label/'points.npz',axis_frame_mm=x,rgb=c)
            missing=p/'position-002/A/points.npz'; saved=missing.read_bytes();missing.unlink()
            damaged=p/'position-006/B/points.npz';good=damaged.read_bytes();damaged.write_bytes(b'unfinished zip')
            pending=p/'position-003/status.json';pending.write_text('{"status":"running"}')
            hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in p.rglob('points.npz')}
            cursor=-1;seen=set();gaps=set();points=0;times=[]
            while cursor<3199:
                t=time.perf_counter();r=preview_page(p,cursor);times.append((time.perf_counter()-t)*1000)
                self.assertLessEqual(r['points'],4096);self.assertLessEqual(len(r['chunks'])+len(r['gaps']),16)
                for c in r['chunks']:
                    self.assertNotIn(c['index'],seen);seen.add(c['index']);points+=len(c['xyz'])
                    for xyz,rgb in zip(c['xyz'],c['rgb']):
                        self.assertEqual(xyz[0]%256,rgb[0]);self.assertEqual(xyz[1],rgb[1])
                gaps.update(g['index'] for g in r['gaps']);self.assertGreater(r['cursor'],cursor);cursor=r['cursor']
            self.assertEqual(gaps,{2,3,6});self.assertIn(3199,seen);self.assertNotIn(3200,seen);self.assertIn(15,seen)
            self.assertLessEqual(points,160000)
            self.assertEqual(hashes,{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in p.rglob('points.npz')})
            missing.write_bytes(saved);damaged.write_bytes(good);pending.write_text('{"status":"complete"}')
            # Stateless fresh call (same behavior after API restart) repairs gaps.
            r=preview_page(p,cursor,'2,3,6');self.assertFalse(r['gaps']);self.assertEqual({c['index'] for c in r['chunks']},gaps)
            self.assertEqual(len(seen|gaps),3200)
            print(json.dumps(dict(positions=len(seen|gaps),last=cursor,p50_ms=float(np.median(times)),p95_ms=float(np.percentile(times,95)),max_points=points),indent=2))

    def test_legacy_and_invalid_cursor(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'position-007').mkdir()
            r=preview_page(p);self.assertEqual(r['available_through'],7)
            self.assertEqual(len(r['gaps']),8)
            with self.assertRaises(ValueError):preview_page(p,4000)
            with self.assertRaises(ValueError):preview_page(p,-1,','.join(map(str,range(20))))

if __name__=='__main__':unittest.main()
