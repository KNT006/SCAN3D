import tempfile,unittest
from pathlib import Path
import cv2,numpy as np
from scan_storage import compress_position,sample_rgb,write_ply

class StorageTests(unittest.TestCase):
    def test_exact_roundtrip_including_marker(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'A').mkdir();im=np.random.default_rng(7).integers(0,256,(20,32,3),dtype=np.uint8)
            cv2.imwrite(str(p/'A/same-frame.ppm'),im);compress_position(p)
            self.assertTrue(np.array_equal(cv2.imread(str(p/'A/same-frame.png')),im))
            self.assertFalse((p/'A/same-frame.ppm').exists())
    def test_color_interpolation(self):
        im=np.array([[[0,20,40],[100,120,140]],[[100,120,140],[200,220,240]]],np.uint8)
        np.testing.assert_array_equal(sample_rgb(im,[[.5,.5]]),[[100,120,140]])
    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'A').mkdir();cv2.imwrite(str(p/'A/same-frame.ppm'),np.zeros((4,4,3),np.uint8))
            (p/'A/same-frame.png').write_bytes(b'old')
            with self.assertRaises(ValueError):compress_position(p)
            self.assertTrue((p/'A/same-frame.ppm').exists())
    def test_ply_record_size(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.ply';write_ply(p,np.ones((2,3)),np.ones((2,3))*128)
            self.assertEqual(len(p.read_bytes().split(b'end_header\n')[1]),30)

if __name__=='__main__':unittest.main()
