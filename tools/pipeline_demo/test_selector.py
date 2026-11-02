import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from selector import ProductionSelector, PointCloudAdapter, geometry_candidates, _fpga
from rk_stripe_strategy import Frame


class SelectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name)/'spatial.json'
        path.write_text(json.dumps(dict(version=1, enabled=True, radius_mm=70, margin_mm=0)))
        self.bundle = _fpga/'new-strategy-bundle'
        self.selector = ProductionSelector(self.bundle, path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_angle_invariant_geometry_matches_production_zero_angle(self):
        original = PointCloudAdapter(self.bundle, geometry_candidates)
        original.spatial_filter = self.selector.adapter.spatial_filter
        uv = np.array([[500., y] for y in range(900, 1800, 3)])
        header = dict(laser_id='A', laser_control='single', complete=True, error=0,
                      calibration=original.hashes, source_frame_id=1, request_id=1,
                      geometry=dict(raw_size_wh=[1920,1080], processing_size_wh=[1080,1920],rotation_cw=90),
                      angle=dict(source='commanded_pulses_no_encoder',moving_before=False,moving_after=False,
                                 emitted_before=0,emitted_after=0,zero_pulses=0,pulses_per_revolution=3200,command_complete=True))
        expected = original.reconstruct(Frame(header, uv))
        actual = self.selector.adapter.reconstruct(Frame({'laser_id':'A'}, uv))
        for key in ('uv','axis_frame_mm','camera_xyz_mm','kept_record_indices'):
            np.testing.assert_allclose(actual[key], expected[key], atol=1e-10)

    def test_full_filter_removes_ground_and_fixed40_weak_points(self):
        records = [(y, 50000, 100, 32768+60, 495,505,500,3000) for y in range(900,1800)]
        result = self.selector.select(records, 'A', None, adaptive=False)
        report = result['report']
        self.assertGreater(report['turntable_filter']['removed_points'], 0)
        self.assertLess(len(result['final_uv']), len(records))
        weak = [(y,num,den,32768+30,lo,hi,k,strength) for y,num,den,tag,lo,hi,k,strength in records]
        self.assertEqual(self.selector.select(weak,'A',None,adaptive=False)['final_uv'], [])
        self.assertFalse(report['adaptive_enabled'])
        self.assertNotIn('axis_frame_mm', result)

    def test_rgb_adaptive_empty_and_invalid_identity(self):
        off = np.zeros((1920,1080,3),np.uint8)
        self.assertEqual(self.selector.select([], 'B', off)['final_uv'], [])
        with self.assertRaises(ValueError):self.selector.select([], 'AB', off)
        with self.assertRaises(ValueError):self.selector.select([], 'A', None)


if __name__ == '__main__':unittest.main()
