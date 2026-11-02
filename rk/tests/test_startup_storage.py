"""No hardware actions: compare startup storage with the actual retention policy."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'rootfs/opt/afc03-scanner/scan3d'))
from storage_budget import startup, GIB, projection
from image_retention import policy, keep


class StartupStorageTests(unittest.TestCase):
    def test_schedule_matches_writer_for_all_supported_steps(self):
        for step in (.1125, .45, 2, 6):
            result = startup(step)
            rules = policy(step, round(360/step))
            expected = [i for i in range(result['positions']) if keep(i, rules)]
            self.assertEqual(result['retained_positions'], len(expected))
            self.assertIn(0, expected)
            self.assertIn(result['positions']-1, expected)
            self.assertEqual(result['compact_positions']+len(expected), result['positions'])

    def test_fine_scan_has_62_images_and_budget_for_compact_data(self):
        result = startup(.1125)
        self.assertEqual(result['retained_positions'], 62)
        self.assertEqual(result['compact_positions'], 3139)
        self.assertEqual(result['required_bytes'], (62*5+3139*2)*1024**2*1.5+GIB)
        self.assertGreater(result['required_bytes'], 10*GIB)
        self.assertLess(result['required_bytes'], 11*GIB)

    def test_coarse_and_capture_keep_startup_reserve(self):
        self.assertEqual(startup(6)['required_bytes'], 3*GIB)
        self.assertEqual(startup(.1125, 'capture')['required_bytes'], 3*GIB)
        self.assertEqual(startup(.1125, 'capture')['retained_positions'], 1)

    def test_runtime_still_blocks_unexpected_growth(self):
        self.assertFalse(projection(12*GIB, [8*1024**2], 3200)['sufficient'])

    def test_invalid_inputs(self):
        for step, mode in [(0, 'scan'), (.1, 'scan'), (6, 'other')]:
            with self.assertRaises(ValueError):
                startup(step, mode)


if __name__ == '__main__':
    unittest.main()
