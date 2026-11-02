"""Read-only scanner presentation gateway. Never writes FPGA/motor/light controls."""
import argparse
import json
import os
from pathlib import Path
import re
import select
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from urllib.request import Request, urlopen
from urllib.error import HTTPError

UPSTREAM = 'http://127.0.0.1:8081/api/scan3d'
ROOT = Path(__file__).resolve().parent
NAME = r'[A-Za-z0-9_-]{1,100}'
HEX = r'[a-f0-9]{32}'


class LivePending(ValueError):
    """Temporary serialization contention, not a camera/eligibility failure."""


class State:
    def __init__(self, device='', code=None):
        self.lock = threading.Lock()
        self.stage = self.revision = 0
        self.instance = str(time.time_ns())
        self.key = dict(configured=bool(device), connected=False, device=device,
                        code=code, error='' if device else 'KEY1 尚未配置')
        self.down = False
        self.last_press = -1.0
        self.press_started = None
        self.on_long_press = None
        self.background = dict(status='unset', error='')

    def snapshot(self):
        with self.lock:
            return dict(stage=self.stage, revision=self.revision, instance=self.instance,
                        key=dict(self.key), background=dict(self.background))

    def change(self, stage=None):
        if stage is not None and (type(stage) is not int or not 0 <= stage < 5):
            raise ValueError('stage 必须为 0..4 的整数')
        with self.lock:
            self.stage = (self.stage + 1) % 5 if stage is None else stage
            self.revision += 1
        return self.snapshot()

    def key_event(self, kind, code, value, now=None):
        now = time.monotonic() if now is None else now
        if kind != 1 or code != self.key['code']:
            return False
        if value == 0:
            started = self.press_started
            self.down = False
            self.press_started = None
            if started is None:
                return False
            if now - started >= 2.0:
                if self.on_long_press:
                    self.on_long_press()
            else:
                self.change()
            return True
        if value != 1 or self.down:
            return False
        self.down = True
        if now - self.last_press < .15:
            return False
        self.last_press = now
        self.press_started = now
        return False  # Decide short/long on release; a long press must not advance.


class StableButton:
    """Active-low GPIO, require stable press AND release before another press."""
    def __init__(self, state):
        self.state = state
        self.observed = self.stable = None
        self.since = 0

    def feed(self, value, now):
        if value != self.observed:
            self.observed, self.since = value, now
        if now - self.since < .03 or value == self.stable:
            return False
        previous, self.stable = self.stable, value
        if previous is not None:
            return self.state.key_event(1, self.state.key['code'], 1 if value == 0 else 0, now)
        return False  # A button held while service starts must not advance.


def listen_key(state, stop, gpio_line=None):
    import fcntl
    while not stop.is_set():
        fd = line_fd = None
        try:
            fd = os.open(state.key['device'], os.O_RDONLY | os.O_NONBLOCK)
            if gpio_line is not None:
                request = bytearray(364)
                struct.pack_into('I', request, 0, gpio_line)
                struct.pack_into('I', request, 256, 1)  # GPIOHANDLE_REQUEST_INPUT
                label = b'scan3d-demo-key1\0'
                request[324:324 + len(label)] = label
                struct.pack_into('I', request, 356, 1)
                fcntl.ioctl(fd, 0xC16CB403, request, True)
                line_fd = struct.unpack_from('i', request, 360)[0]
            with state.lock:
                state.key.update(connected=True, error='')
            state.down = False
            state.press_started = None
            stable = StableButton(state)
            event = struct.Struct('@llHHi')
            pending = b''
            while not stop.is_set():
                if line_fd is not None:
                    values = bytearray(64)
                    fcntl.ioctl(line_fd, 0xC040B408, values, True)
                    stable.feed(values[0], time.monotonic())
                    stop.wait(.01)
                elif select.select([fd], [], [], .2)[0]:
                    chunk = os.read(fd, event.size * 16)
                    if not chunk:
                        raise OSError('按键设备断开')
                    pending += chunk
                    while len(pending) >= event.size:
                        _, _, kind, code, value = event.unpack(pending[:event.size])
                        pending = pending[event.size:]
                        state.key_event(kind, code, value)
        except (OSError, ValueError) as exc:
            with state.lock:
                state.key.update(connected=False, error=str(exc))
        finally:
            if line_fd is not None:
                os.close(line_fd)
            if fd is not None:
                os.close(fd)
        stop.wait(2)


def read_upstream(path, body=None, timeout=10):
    request = Request(UPSTREAM + path,
                      data=None if body is None else json.dumps(body).encode(),
                      headers={} if body is None else {'Content-Type': 'application/json'})
    try:
        with urlopen(request, timeout=timeout) as response:
            data = response.read(24 * 1024 * 1024 + 1)
            if len(data) > 24 * 1024 * 1024:
                raise ValueError('上游响应超过展示预算')
            return response.status, response.headers.get('Content-Type', 'application/json'), data
    except HTTPError as exc:
        return exc.code, 'application/json', exc.read(16000)


def is_busy(status):
    helper = status.get('helper', {})
    return bool(status.get('active') or status.get('mesh_processing') or status.get('ai_processing') or
                helper.get('worker_running') or helper.get('manual_motion') or helper.get('unavailable'))


def live_busy(status, background=False):
    # Manual rotation is allowed for live observation, never for saving OFF.
    helper = status.get('helper', {})
    return bool(status.get('active') or status.get('mesh_processing') or status.get('ai_processing') or
                helper.get('worker_running') or helper.get('unavailable') or
                (background and helper.get('manual_motion')))


def proxy_path(path):
    if path == '/api/runs':
        return '/runs'
    m = re.fullmatch('/api/runs/(' + NAME + ')/details', path)
    if m:
        return '/runs/' + m[1] + '/details'
    m = re.fullmatch('/api/image/(' + NAME + r')/(\d{1,4})/(OFF|A|B|COLOR)', path)
    if m and int(m[2]) <= 3200:
        return '/runs/' + m[1] + '/image/' + m[2] + '/' + m[3]
    m = re.fullmatch('/api/replay/(' + HEX + ')', path)
    if m:
        return '/replay/' + m[1]
    return None


def replay_body(body):
    if not isinstance(body, dict) or not isinstance(body.get('run'), str) or not re.fullmatch(NAME, body['run']):
        raise ValueError('无效档案名')
    if type(body.get('index')) is not int or not 0 <= body['index'] <= 3200 or body.get('laser') not in ('A', 'B'):
        raise ValueError('无效帧或激光通道')
    return dict(run=body['run'], index=body['index'], laser=body['laser'], mode='current_scan')


class Application:
    def __init__(self, state):
        self.state = state
        self.camera_lock = threading.Lock()
        self.camera_cache = None
        self.runs_lock = threading.Lock()
        self.runs_cache = None
        self.replay_lock = threading.Lock()
        self.live_lock = threading.Lock()
        self.live_processor = None
        self.background_stale = False
        self.motion_stamp = None
        self.background_request_lock = threading.Lock()
        self.state.on_long_press = self.request_background
        self.shared_lock = threading.Lock()
        self.shared_generation = 0
        self.shared_cache = {}  # At most one result/error per stage.
        self.shared_running = False
        self.shared_wanted = None
        self.shared_wanted_at = 0.0
        self.shared_last_attempt = -1.0

    def invalidate_live_cache(self):
        with self.shared_lock:
            self.shared_generation += 1
            self.shared_cache.clear()
            self.shared_wanted = None

    def shared_live(self, stage):
        """Fast poll: share one native computation across all browser viewers."""
        if type(stage) is not int or not 0 <= stage < 5:
            raise ValueError('stage must be 0..4')
        now = time.monotonic()
        with self.shared_lock:
            pending = dict(pending=True, stage=stage, retry_after_ms=100,
                           background_generation=self.shared_generation)
            if self.background_request_lock.locked():
                return 202, pending
            self.shared_wanted, self.shared_wanted_at = stage, now
            self.shared_cache = {k: v for k, v in self.shared_cache.items() if now - v[0] <= 3.0}
            entry = self.shared_cache.get(stage)
            refresh_after = .1 if entry is None or entry[1] == 200 else .5
            if (not self.shared_running and
                (entry is None or now - entry[0] >= refresh_after) and
                now - self.shared_last_attempt >= .1):
                self.shared_running = True
                threading.Thread(target=self._shared_worker, daemon=True).start()
            if entry is not None:
                _, code, data = entry
                return code, dict(data, cache_age_ms=round((now-entry[0])*1000, 2),
                                  background_generation=self.shared_generation)
            return 202, pending

    def _shared_worker(self):
        # No frame FIFO. Requests during processing only replace the latest stage.
        while True:
            with self.shared_lock:
                stage, generation = self.shared_wanted, self.shared_generation
                if stage is None or self.background_request_lock.locked():
                    self.shared_running = False
                    return
                self.shared_last_attempt = time.monotonic()
            try:
                data, code = self.live(stage=stage), 200
            except LivePending:
                data, code = None, 202
            except Exception as exc:
                data, code = dict(error=str(exc), stage=stage), 503
            with self.shared_lock:
                if generation == self.shared_generation and code != 202:
                    if code == 503:
                        # A newly observed invalid device state invalidates all views.
                        self.shared_cache.clear()
                    self.shared_cache[stage] = (time.monotonic(), code, data)
                if (generation == self.shared_generation and self.shared_wanted != stage and
                    self.shared_wanted is not None and
                    time.monotonic() - self.shared_wanted_at <= 1.0 and
                    not self.background_request_lock.locked()):
                    continue
                self.shared_running = False
                return

    def request_background(self):
        if not self.background_request_lock.acquire(False):
            return
        with self.state.lock:
            self.state.background = dict(status='capturing', error='')
        def capture():
            try:
                result = self.live(background=True)
                with self.state.lock:
                    self.state.background = dict(status='ready', error='', frame=result['background'])
                self.state.change(0)
                print('KEY1 background ready', result['background'], flush=True)
            except Exception as exc:
                with self.state.lock:
                    self.state.background = dict(status='error', error=str(exc))
                print('KEY1 background rejected:', str(exc), flush=True)
            finally:
                self.background_request_lock.release()
        threading.Thread(target=capture, daemon=True).start()

    def observe_motion(self, status):
        path = Path('/userdata/afc03-scanner/jobs/scan3d-controls')
        stamp = path.stat().st_mtime_ns if path.exists() else None
        self.background_stale |= bool(status.get('helper', {}).get('manual_motion'))
        if self.motion_stamp is not None and stamp != self.motion_stamp:
            self.background_stale = True
        return stamp

    def live(self, background=False, stage=None):
        if stage is not None and (type(stage) is not int or not 0 <= stage < 5):
            raise ValueError('stage must be 0..4')
        if background:
            self.invalidate_live_cache()
        if not background and self.background_request_lock.locked():
            raise LivePending('正在保存背景，请稍候')
        if not self.live_lock.acquire(timeout=3 if background else 0):
            raise LivePending('实时条纹处理尚未完成，请等待')
        try:
            started = time.perf_counter()
            # Query once to select A/B; subsequent frames do not query device state.
            if background or not hasattr(self, 'demo_status'):
                code, _, data = read_upstream('/status', timeout=4)
                status = json.loads(data)
                if code != 200:
                    raise ValueError('无法初始化演示通道')
                if not background and status.get('helper', {}).get('manual_laser', {}).get('channel') in ('A', 'B'):
                    self.demo_status = status
            else:
                code, status = 200, self.demo_status
            if background and live_busy(status, background):
                raise ValueError('扫描或其他处理正在运行，实时条纹已让出资源')
            light = status.get('helper', {}).get('manual_laser', {})
            before_stamp = self.observe_motion(status)
            channel = light.get('channel', 'UNKNOWN')
            if background and channel != 'OFF':
                raise ValueError('请先关闭两束激光，再保存背景')
            if not background and channel not in ('A', 'B'):
                raise ValueError('请仅开启 A 或 B 一束激光，再进行实时提取')
            if not background and not hasattr(self, 'background_light'):
                raise ValueError('尚无原始背景，请先关闭激光并保存背景')
            if self.live_processor is None:
                from live import LiveProcessor
                self.live_processor = LiveProcessor(ROOT / 'spatial_mask.hex', status['scan_roi'])
            before_capture = time.perf_counter()
            with urlopen('http://127.0.0.1:8080/capture.ppm', timeout=7) as response:
                ppm = response.read(1920 * 1080 * 3 + 128)
                meta = dict(stream_id=response.headers.get('X-Raw-Stream'),
                            sequence=int(response.headers.get('X-Raw-Sequence', '-1')),
                            pts_ns=response.headers.get('X-Raw-PTS-Ns'))
            captured = time.perf_counter()
            if background:
                code, _, data = read_upstream('/status', timeout=4)
                after = json.loads(data)
            else:
                code, after = 200, status
            after_stamp = self.observe_motion(after)
            if background and (code != 200 or live_busy(after, background) or after.get('helper', {}).get('manual_laser') != light):
                raise ValueError('采帧期间设备状态改变，请重新采集')
            if background:
                if before_stamp != after_stamp:
                    raise ValueError('保存背景期间有手动操作，请停稳后重试')
                result = self.live_processor.set_background(ppm, meta)
                self.__dict__.pop('demo_status', None)
                self.background_light = light.get('led')
                self.background_stale = False
                self.motion_stamp = after_stamp
                self.invalidate_live_cache()
                return result
            if getattr(self, 'background_light', None) != light.get('led'):
                raise ValueError('照明已变化或尚无背景，请重新保存关激光背景')
            checked = time.perf_counter()
            result = self.live_processor.process(ppm, meta, channel, adaptive=not self.background_stale, stage=stage)
            result['timings'].update(status_before_ms=(before_capture-started)*1000,
                                     capture_ms=(captured-before_capture)*1000,
                                     status_after_ms=(checked-captured)*1000,
                                     request_ms=(time.perf_counter()-started)*1000)
            return result
        finally:
            self.live_lock.release()

    def cached(self, path, lock, attribute, seconds):
        if not lock.acquire(False):
            cache = getattr(self, attribute)
            if cache and time.monotonic() - cache[0] < seconds:
                return cache[1]
            return 429, 'application/json', b'{"error":"request pending"}'
        try:
            cache = getattr(self, attribute)
            if cache and time.monotonic() - cache[0] < seconds:
                return cache[1]
            response = read_upstream(path)
            if response[0] == 200:
                setattr(self, attribute, (time.monotonic(), response))
            return response
        finally:
            lock.release()


def handler_class(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, code, kind, data):
            try:
                self.send_response(code)
                self.send_header('Content-Type', kind)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def json(self, code, data):
            self.reply(code, 'application/json; charset=utf-8', json.dumps(data, ensure_ascii=False).encode())

        def do_GET(self):
            path = urlsplit(self.path).path
            try:
                if path == '/':
                    return self.reply(200, 'text/html; charset=utf-8', (ROOT / 'index.html').read_bytes())
                if path == '/app.js':
                    return self.reply(200, 'text/javascript; charset=utf-8', (ROOT / 'app.js').read_bytes())
                if path == '/api/state':
                    return self.json(200, app.state.snapshot())
                if path == '/api/live/frame':
                    query = parse_qs(urlsplit(self.path).query)
                    stage = int(query['stage'][0]) if 'stage' in query else None
                    if stage is not None:
                        return self.json(*app.shared_live(stage))
                    return self.json(200, app.live())
                if path == '/camera.jpg':
                    return self.reply(*app.cached('/preview.jpg', app.camera_lock, 'camera_cache', .1))
                if path == '/api/runs':
                    return self.reply(*app.cached('/runs', app.runs_lock, 'runs_cache', 10))
                target = proxy_path(path)
                if target:
                    return self.reply(*read_upstream(target, timeout=20))
                return self.json(404, {'error': '接口不存在'})
            except Exception as exc:
                self.json(503, {'error': str(exc)})

        def do_POST(self):
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + self.headers.get('Host', ''):
                return self.json(403, {'error': '仅允许同源操作'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 2048:
                    return self.json(400, {'error': '无效请求长度'})
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('请求需为对象')
                path = urlsplit(self.path).path
                if path == '/api/live/background':
                    return self.json(200, app.live(background=True))
                if path == '/api/next':
                    return self.json(200, app.state.change())
                if path == '/api/stage':
                    if 'stage' not in body:
                        raise ValueError('缺少 stage')
                    return self.json(200, app.state.change(body['stage']))
                if path == '/api/replay':
                    request = replay_body(body)
                    if not app.replay_lock.acquire(False):
                        return self.json(409, {'error': '回放请求正在提交'})
                    try:
                        code, _, data = read_upstream('/status', timeout=4)
                        if code != 200 or is_busy(json.loads(data)):
                            return self.json(409, {'error': '扫描、运动或点云处理优先，暂不启动回放'})
                        return self.reply(*read_upstream('/replay', request, timeout=8))
                    finally:
                        app.replay_lock.release()
                self.json(404, {'error': '接口不存在'})
            except (ValueError, TypeError) as exc:
                self.json(400, {'error': str(exc)})
            except Exception as exc:
                self.json(503, {'error': str(exc)})
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bind', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8840)
    parser.add_argument('--key-device', default=os.environ.get('DEMO_KEY_DEVICE', ''))
    parser.add_argument('--key-code', type=int, default=int(os.environ.get('DEMO_KEY_CODE', '0')))
    parser.add_argument('--gpio-chip', default='')
    parser.add_argument('--gpio-line', type=int, default=15)
    args = parser.parse_args()
    if args.gpio_chip and (not re.fullmatch(r'/dev/gpiochip\d+', args.gpio_chip) or not 0 <= args.gpio_line <= 31):
        parser.error('invalid GPIO input')
    if args.key_device and not re.fullmatch(r'/dev/input/event\d+', args.key_device):
        parser.error('invalid evdev input')
    state = State(args.gpio_chip or args.key_device, args.gpio_line if args.gpio_chip else args.key_code)
    app = Application(state)
    stop = threading.Event()
    if state.key['configured']:
        threading.Thread(target=listen_key, args=(state, stop, args.gpio_line if args.gpio_chip else None), daemon=True).start()
    server = ThreadingHTTPServer((args.bind, args.port), handler_class(app))
    try:
        server.serve_forever()
    finally:
        stop.set()
        server.server_close()


if __name__ == '__main__':
    main()
