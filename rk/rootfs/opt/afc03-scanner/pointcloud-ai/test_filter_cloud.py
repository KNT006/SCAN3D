import tempfile
import unittest
from pathlib import Path
import numpy as np
from filter_cloud import load_cloud, preprocess, select_points, project_pixels
import cv2


class FilterTests(unittest.TestCase):
    def test_projection_matches_opencv(self):
        rng = np.random.default_rng(42)
        points = rng.uniform([-60, -60, 120], [60, 60, 300], size=(100000, 3))
        matrix = np.array([[1585., 0, 489], [0, 1590., 965], [0, 0, 1.]])
        for distortion in (np.array([.177, -.277, -.00019, -.00236, .01]), np.zeros(8)):
            expected = cv2.projectPoints(points, np.zeros(3), np.zeros(3), matrix, distortion)[0][:, 0]
            actual = project_pixels(points, matrix, distortion)
            np.testing.assert_allclose(actual, expected, rtol=1e-13, atol=1e-10)
            np.testing.assert_array_equal(np.rint(actual), np.rint(expected))

    def test_unknown_views_do_not_delete(self):
        rejected = select_points(np.array([0, 3, 4, 5]), np.array([0, 31, 31, 31]), 31, .13)
        np.testing.assert_array_equal(rejected, [False, False, False, True])

    def test_preprocessing(self):
        result = preprocess(np.zeros((50, 60, 3), np.uint8))
        self.assertEqual(result.shape, (320, 320, 3))
        self.assertEqual(result.dtype, np.float32)
        self.assertTrue(np.isfinite(result).all())

    def test_preserve_source_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'cloud.npz'
            np.savez(path, xyz=np.ones((2, 3), np.float32), rgb=np.ones((2, 3), np.uint8), position=[1, 2], inferred=[0, 1])
            fields = load_cloud(path)
            np.testing.assert_array_equal(fields['position'], [1, 2])
            np.testing.assert_array_equal(fields['inferred'], [0, 1])

    def test_reject_nonfinite_coordinates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'cloud.npz'
            np.savez(path, xyz=[[np.nan, 0, 0]], rgb=[[0, 0, 0]])
            with self.assertRaises(ValueError):
                load_cloud(path)


if __name__ == '__main__':
    unittest.main()
