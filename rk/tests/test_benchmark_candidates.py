import sys, unittest, tempfile
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/heterogeneous_benchmark'))
from candidates import extract_candidates, load_rom_mask, compare_uv
from compare_spatial_candidates import reference_row

class CandidateBenchmarkTests(unittest.TestCase):
    def test_batched_matches_scalar_oracle(self):
        rng = np.random.default_rng(123)
        off = np.zeros((1920,1080,3), np.uint8)
        on = off.copy()
        roi = [140,1000,880,1006]
        x = np.arange(1080)
        for y in range(1000,1006):
            signal = rng.integers(0,6,1080).astype(float)
            for k,h,w in ((230,90,3),(420,180,5),(700,35,2)):
                signal += h * np.exp(-((x-k-(y%3)) / w)**2)
            on[y,:,0] = np.clip(signal,0,255)
        mask = np.zeros((6,1080),bool)
        actual = extract_candidates(on,off,roi,mask)
        expected=[]
        for y in range(1000,1006):
            expected += [(y,*r) for r in reference_row(on[y],off[y],140,879,np.zeros(1080,bool),np.zeros(1080))]
        self.assertEqual(actual,expected)
        self.assertTrue(actual)
        self.assertTrue(compare_uv(actual,[[r[1]/r[2],r[0]] for r in expected])['passed'])

    def test_rom_intervals_and_laser_offset(self):
        words=[0xfff | (0xfff << 24)]*4096
        words[1000]=150 | (170 << 12) | (500 << 24) | (505 << 36)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'rom.hex';p.write_text(''.join(f'{w:012x}\n' for w in words))
            a=load_rom_mask(p,'A',[140,1000,880,1001])
            b=load_rom_mask(p,'B',[140,1000,880,1001])
            self.assertEqual(int(a.sum()),27)
            self.assertEqual(int(b.sum()),0)
            self.assertTrue(a[0,150] and a[0,170] and a[0,505])
            self.assertFalse(a[0,171])

    def test_empty_and_mismatch(self):
        self.assertTrue(compare_uv([],[])['passed'])
        self.assertFalse(compare_uv([],[[1,2]])['passed'])
        self.assertFalse(compare_uv([(2,10,1,0,0,0,0,0)],[[11,2]])['passed'])

if __name__=='__main__':unittest.main()
