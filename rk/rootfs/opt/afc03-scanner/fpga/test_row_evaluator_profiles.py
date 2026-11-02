"""Golden row records for default and wide-core evaluator profiles."""
import hashlib
import json
import unittest

import numpy as np
import row_model
import offline_shared_extractor as shared


class EvaluatorProfileTests(unittest.TestCase):
    def test_baseline_records(self):
        # Captured before replacing source-string rewriting with explicit parameters.
        rng = np.random.default_rng(3576)
        digest = hashlib.sha256()
        for case in range(256):
            off = rng.integers(0, 40, (160, 3), dtype=np.uint8)
            x = np.arange(160)
            profile = np.zeros(160)
            for _ in range(1 + case % 4):
                center = int(rng.integers(0, 160))
                width = float(rng.uniform(1, 22))
                height = int(rng.integers(20, 256))
                profile += height * np.exp(-((x - center) / width) ** 2)
            on = np.clip(off.astype(float) + profile[:, None]
                         + rng.integers(0, 8, (160, 3)), 0, 255).astype(np.uint8)
            signal, rawmax, smooth, base, peaks = row_model.prepare(on, off, 4, 155)
            args = (signal, rawmax, smooth, base, peaks, 4, 155)
            records = [row_model.evaluate(*args), shared.evaluate(*args)]
            digest.update(json.dumps(records, sort_keys=True).encode())
        self.assertEqual(digest.hexdigest(),
                         '994b5d262e2a78a7d4d4bb0e2cb0c4f75df2b81dd246d6d2d15041ad192d1892')


if __name__ == '__main__':
    unittest.main()
