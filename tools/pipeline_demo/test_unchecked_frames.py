import unittest
from unittest.mock import patch, MagicMock
import server

class UncheckedFrames(unittest.TestCase):
    def test_initialized_frames_do_not_query_status(self):
        app=server.Application(server.State())
        app.demo_status={'helper':{'manual_laser':{'channel':'A','led':0}}}
        app.background_light=0
        app.live_processor=MagicMock()
        app.live_processor.process.side_effect=lambda *a,**k: {'timings':{}}
        response=MagicMock()
        response.__enter__.return_value=response
        response.headers={'X-Raw-Stream':'test','X-Raw-Sequence':'2'}
        response.read.return_value=b'frame'
        with patch.object(server,'read_upstream',side_effect=AssertionError('unexpected status query')), patch.object(server,'urlopen',return_value=response):
            app.live(stage=4)
            app.live(stage=4)
        self.assertEqual(app.live_processor.process.call_count,2)
