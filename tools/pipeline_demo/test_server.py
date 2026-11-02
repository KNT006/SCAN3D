import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch
import server


class Tests(unittest.TestCase):
    def wait_shared(self, app):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            with app.shared_lock:
                if not app.shared_running:
                    return
            time.sleep(.005)
        self.fail('shared worker did not finish')

    def test_shared_viewers_one_worker_no_pending_failure(self):
        app = server.Application(server.State())
        entered, release = threading.Event(), threading.Event()
        calls=[]
        def live(stage):
            calls.append(stage);entered.set();self.assertTrue(release.wait(2))
            return {'stage':stage,'frame':{'sequence':10},'images':{}}
        with patch.object(app, 'live', side_effect=live):
            self.assertEqual(app.shared_live(4)[0],202)
            self.assertTrue(entered.wait(1))
            with ThreadPoolExecutor(max_workers=8) as pool:
                responses = list(pool.map(app.shared_live, [4]*20))
            self.assertTrue(all(code==202 and data['pending'] for code,data in responses))
            self.assertEqual(calls,[4])
            release.set();self.wait_shared(app)
            for _ in range(10):
                code,data=app.shared_live(4)
                self.assertEqual(code,200);self.assertEqual(data['frame']['sequence'],10)
            self.assertEqual(calls,[4])

    def test_shared_rapid_switch_uses_latest_not_fifo(self):
        app=server.Application(server.State())
        entered,release=threading.Event(),threading.Event();calls=[]
        def live(stage):
            calls.append(stage)
            if stage==1:entered.set();self.assertTrue(release.wait(2))
            return {'stage':stage,'frame':{'sequence':stage}}
        with patch.object(app,'live',side_effect=live):
            app.shared_live(1);self.assertTrue(entered.wait(1))
            for stage in (2,3,2,4):self.assertEqual(app.shared_live(stage)[0],202)
            release.set();self.wait_shared(app)
            self.assertEqual(calls,[1,4])
            self.assertEqual(app.shared_live(4)[1]['stage'],4)
            self.assertLessEqual(len(app.shared_cache),5)

    def test_shared_background_generation_discards_old_work(self):
        app=server.Application(server.State())
        entered,release=threading.Event(),threading.Event()
        def live(stage):
            entered.set();self.assertTrue(release.wait(2));return {'stage':stage,'frame':{'sequence':1}}
        with patch.object(app,'live',side_effect=live):
            app.shared_live(4);self.assertTrue(entered.wait(1))
            app.invalidate_live_cache();release.set();self.wait_shared(app)
            self.assertEqual(app.shared_cache,{})
        app.background_request_lock.acquire()
        try:self.assertEqual(app.shared_live(4)[0],202)
        finally:app.background_request_lock.release()

    def test_shared_expiry_real_error_and_transient_pending(self):
        app=server.Application(server.State())
        app.shared_cache[4]=(time.monotonic()-4,200,{'stage':4,'frame':{'sequence':1}})
        with patch.object(app,'live',side_effect=server.LivePending('processing')):
            code,data=app.shared_live(4);self.assertEqual(code,202)
            self.assertNotIn('frame',data);self.wait_shared(app);self.assertEqual(app.shared_cache,{})
        app.shared_last_attempt=-1
        with patch.object(app,'live',side_effect=ValueError('laser OFF')):
            self.assertEqual(app.shared_live(4)[0],202);self.wait_shared(app)
            code,data=app.shared_live(4)
            self.assertEqual(code,503);self.assertEqual(data['error'],'laser OFF')

    def test_live_allows_manual_rotation_but_blocks_capture_and_scan(self):
        moving = {'helper': {'manual_motion': True}}
        self.assertFalse(server.live_busy(moving))
        self.assertTrue(server.live_busy(moving, background=True))
        self.assertTrue(server.is_busy(moving))
        for status in [{'active':'scan'}, {'mesh_processing':True}, {'ai_processing':True},
                       {'helper':{'worker_running':True}}, {'helper':{'unavailable':True}}]:
            self.assertTrue(server.live_busy(status))
    def test_press_repeat_release_debounce(self):
        s = server.State('/dev/input/event6', 28)
        self.assertFalse(s.key_event(1, 99, 1, 1))
        self.assertFalse(s.key_event(1, 28, 1, 1))
        self.assertFalse(s.key_event(1, 28, 2, 1.1))
        self.assertFalse(s.key_event(1, 28, 1, 1.2))
        s.key_event(1, 28, 0, 1.3)
        self.assertFalse(s.key_event(1, 28, 1, 1.4))
        self.assertTrue(s.key_event(1, 28, 0, 1.6))
        self.assertEqual(s.snapshot()['stage'], 2)

    def test_long_press_on_release_once_no_stage_change(self):
        s = server.State('key', 15)
        calls=[];s.on_long_press=lambda:calls.append('background')
        s.key_event(1,15,1,1)
        s.key_event(1,15,2,4)
        self.assertEqual(calls,[])
        self.assertEqual(s.stage,0)
        s.key_event(1,15,0,4.1)
        s.key_event(1,15,0,4.2)
        self.assertEqual(calls,['background'])
        self.assertEqual(s.stage,0)

    def test_background_worker_success_and_refusal(self):
        app=server.Application(server.State())
        def wait_worker():
            self.assertTrue(app.background_request_lock.acquire(timeout=2))
            app.background_request_lock.release()
        with patch.object(app,'live',return_value={'background':{'sequence':22}}):
            app.state.change(3);app.request_background();wait_worker()
            self.assertEqual(app.state.snapshot()['background']['status'],'ready')
            self.assertEqual(app.state.stage,0)
        with patch.object(app,'live',side_effect=ValueError('laser ON')):
            app.state.change(3);app.request_background();wait_worker()
            self.assertEqual(app.state.snapshot()['background']['error'],'laser ON')
            self.assertEqual(app.state.stage,3)

    def test_gpio_bounce_held_and_release(self):
        s = server.State('/dev/gpiochip1', 15)
        b = server.StableButton(s)
        for t, v in [(0, 1), (.04, 1), (.1, 0), (.11, 1), (.12, 0), (.16, 0), (.2, 0), (.5, 1), (.54, 1), (.7, 0), (.74, 0)]:
            b.feed(v, t)
        self.assertEqual(s.snapshot()['stage'], 1)
        s2 = server.State('/dev/gpiochip1', 15)
        b = server.StableButton(s2)
        b.feed(0, 0); b.feed(0, .04)
        self.assertEqual(s2.snapshot()['stage'], 0)

    def test_paths_and_payload(self):
        for bad in ['/api/image/../0/A', '/api/image/run/3201/A', '/api/image/run/0/no', '/api/replay/xyz', '/api/control']:
            self.assertIsNone(server.proxy_path(bad))
        self.assertEqual(server.proxy_path('/api/image/scan-1/3200/B'), '/runs/scan-1/image/3200/B')
        for bad in [dict(run='../a', index=0, laser='A'), dict(run='a', index=True, laser='A'), dict(run='a', index=0, laser='X')]:
            with self.assertRaises(ValueError): server.replay_body(bad)
        self.assertEqual(server.replay_body(dict(run='a', index=0, laser='B', parameters={'unsafe': 1})), dict(run='a', index=0, laser='B', mode='current_scan'))

    def test_api_state_and_busy_gate(self):
        s = server.State()
        app = server.Application(s)
        http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.handler_class(app))
        threading.Thread(target=http.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:' + str(http.server_port)
        def post(path, body, origin=None):
            headers = {'Content-Type': 'application/json'}
            if origin: headers['Origin'] = origin
            return urlopen(Request(base + path, data=json.dumps(body).encode(), headers=headers))
        try:
            self.assertEqual(json.load(post('/api/next', {}))['stage'], 1)
            self.assertEqual(json.load(post('/api/stage', {'stage': 4}))['stage'], 4)
            self.assertEqual(json.load(post('/api/next', {}))['stage'], 0)
            with self.assertRaises(HTTPError) as e: post('/api/stage', {'stage': True})
            self.assertEqual(e.exception.code, 400)
            with self.assertRaises(HTTPError) as e: post('/api/next', {}, 'http://other')
            self.assertEqual(e.exception.code, 403)
            with patch('server.read_upstream', return_value=(200, 'application/json', b'{"active":"scan"}')) as upstream:
                with self.assertRaises(HTTPError) as e: post('/api/replay', dict(run='r', index=0, laser='A'))
                self.assertEqual(e.exception.code, 409)
                self.assertEqual(upstream.call_count, 1)
        finally:
            http.shutdown(); http.server_close()

    def test_camera_failure_does_not_serve_stale_frame(self):
        app = server.Application(server.State())
        app.camera_cache = (0, (200, 'image/jpeg', b'old'))
        with patch('server.read_upstream', return_value=(503, 'application/json', b'error')):
            self.assertEqual(app.cached('/preview.jpg', app.camera_lock, 'camera_cache', .3)[0], 503)


if __name__ == '__main__':
    unittest.main()
