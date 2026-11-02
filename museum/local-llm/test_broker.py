"""Run on Linux: admission must fail before loading the NPU model."""
import unittest
from unittest.mock import patch
from uuid import uuid4
import broker


class AdmissionTests(unittest.TestCase):
    def request(self):
        return dict(id=str(uuid4()), prompt='hello')

    @patch.object(broker, 'locked', return_value=True)
    def test_scanner_busy(self, _):
        e = broker.Engine()
        self.assertEqual(e.run(self.request())[0], 409)
        self.assertIsNone(e.proc)

    @patch.object(broker, 'locked', return_value=False)
    @patch.object(broker, 'available_mib', return_value=500)
    def test_low_memory(self, *_):
        e = broker.Engine()
        self.assertEqual(e.run(self.request())[0], 503)
        self.assertIsNone(e.proc)

    @patch.object(broker, 'locked', return_value=False)
    @patch.object(broker, 'available_mib', return_value=2500)
    @patch.object(broker, 'swap_enabled', return_value=True)
    def test_swap_refused(self, *_):
        e = broker.Engine()
        self.assertEqual(e.run(self.request())[0], 503)
        self.assertIsNone(e.proc)

    def test_cancel_before_dispatch(self):
        e = broker.Engine()
        r = self.request()
        e.stop('cancel', r['id'])
        self.assertEqual(e.run(r)[0], 409)
        self.assertIsNone(e.proc)


if __name__ == '__main__':
    unittest.main()
