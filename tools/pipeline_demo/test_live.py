import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from live import LiveProcessor
from candidates import extract_candidates


def ppm(rotated):
    raw = cv2.rotate(rotated, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return cv2.imencode('.ppm', raw)[1].tobytes()


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name) / 'rom.hex'
        words = [0xfff | (0xfff << 24)] * 4096
        # B excludes the test stripe; A retains it.
        for y in range(1000,1006):
            words[2048+y] = 200 | (300 << 12) | (0xfff << 24)
        path.write_text(''.join(f'{w:012x}\n' for w in words))
        self.roi = [140,1000,880,1006]
        class Selector:
            def select(self, records, laser, off_rgb, adaptive=True):
                return dict(final_uv=[[r[1]/r[2],r[0]] for r in records], report={}, stage_counts={})
        self.processor = LiveProcessor(path, self.roi, selector=Selector())
        self.off = np.zeros((1920,1080,3), np.uint8)
        self.on = self.off.copy()
        x = np.arange(1080)
        for y in range(1000,1006):
            self.on[y,:,0] = (180*np.exp(-((x-250)/4)**2)).astype(np.uint8)
        self.processor.set_background(ppm(self.off), dict(stream_id='camera', sequence=10))

    def test_native_reference_parity_and_same_frame_preview(self):
        actual = self.processor.process(ppm(self.on), dict(stream_id='camera',sequence=11), 'A')
        expected = extract_candidates(self.on,self.off,self.roi,self.processor.masks['A'])
        self.assertTrue(expected)
        self.assertEqual(actual['records'], expected)
        self.assertEqual(actual['frame']['sequence'],11)
        self.assertEqual(actual['background']['sequence'],10)
        self.assertEqual(set(actual['images']), {'original','difference','smooth'})
        image = cv2.imdecode(np.frombuffer(base64.b64decode(actual['images']['original'].split(',')[1]),np.uint8),1)
        self.assertEqual(image.shape,(960,540,3))
        self.assertEqual(self.processor.process(ppm(self.on),dict(stream_id='camera',sequence=12),'B')['count'],0)

    def test_stage_specific_output_preserves_candidates_and_final(self):
        data = ppm(self.on)
        meta = dict(stream_id='camera', sequence=11)
        full = self.processor.process(data, meta, 'A')
        for stage, keys in enumerate(({'original'}, {'difference'}, {'smooth'}, {'original'}, set())):
            with patch('live.extract_candidates', wraps=extract_candidates) as extract, patch.object(
                    self.processor.selector, 'select', wraps=self.processor.selector.select) as select:
                result = self.processor.process(data, meta, 'A', stage=stage)
                self.assertEqual(extract.call_count, int(stage >= 3))
                self.assertEqual(select.call_count, int(stage >= 3))
            self.assertEqual(set(result['images']), keys)
            self.assertNotIn('records', result)
            for key in keys:
                self.assertEqual(result['images'][key], full['images'][key])
            if stage >= 3: self.assertEqual(result['uv'], full['uv'])
            if stage >= 3: self.assertEqual(result['final_uv'], full['final_uv'])
        for stage in (-1,5,True,'4'):
            with self.assertRaises(ValueError): self.processor.process(data, meta, 'A', stage=stage)

    def test_requires_background_current_stream_and_native_frame(self):
        for image,meta in [(ppm(self.on),dict(stream_id='other',sequence=11)),
                           (ppm(self.on),dict(stream_id='camera',sequence=10)),
                           (b'bad',dict(stream_id='camera',sequence=11))]:
            with self.assertRaises(ValueError): self.processor.process(image,meta,'A')
        self.processor.off=None
        with self.assertRaises(ValueError): self.processor.process(ppm(self.on),dict(stream_id='camera',sequence=11),'A')


if __name__ == '__main__':
    unittest.main()
