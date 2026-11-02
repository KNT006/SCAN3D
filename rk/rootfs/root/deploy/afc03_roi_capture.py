"""One-shot RGB ROI diagnostic capture. No hardware access and no GStreamer import.

The diagnostic marker occupies the first four native RGB pixels (12 bytes):
little-endian uint32 magic 0x31544752, host token, FPGA frame id. Never use JPEG
or rotated preview pixels for this comparison. Only one full frame is retained.
"""
import json
import struct
import threading
import time
from urllib.parse import parse_qs, urlsplit

MAGIC = 0x31544752
PREFIX = '/diagnostic/roi/'


class CaptureError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class RoiTokenCapture:
    def __init__(self, stream_id, width=1920, height=1080, clock=time.monotonic,
                 max_wait_s=30.0, retention_s=60.0):
        self.width, self.height = width, height
        self.expected_bytes = width * height * 3
        self.header = ('P6\n%d %d\n255\n' % (width, height)).encode('ascii')
        self.clock = clock
        self.max_wait_s, self.retention_s = max_wait_s, retention_s
        self.lock = threading.Lock()
        self.stream_id = stream_id
        self.generation = 0
        self.state = 'idle'
        self.token = None
        self.frame = self.meta = None
        self.deadline = None
        self.error = None
        self.candidates = self.prefix_misses = 0

    def _discard(self, state, error=None):
        self.state, self.error = state, error
        self.frame = self.meta = None
        self.deadline = None

    def _refresh(self, stream_id):
        if stream_id != self.stream_id:
            self.stream_id = stream_id
            self._discard('invalid', 'stream_changed')
        elif self.deadline is not None and self.clock() >= self.deadline:
            self._discard('expired', 'capture_timeout' if self.state != 'ready'
                          else 'retention_expired')

    def _status(self):
        return dict(state=self.state, generation=self.generation, token=self.token,
                    stream_id=self.stream_id, width=self.width, height=self.height,
                    error=self.error, candidates=self.candidates,
                    prefix_misses=self.prefix_misses,
                    seconds_remaining=max(0.0, self.deadline-self.clock())
                    if self.deadline is not None else None,
                    frame=dict(self.meta) if self.meta is not None else None)

    def status(self, stream_id):
        with self.lock:
            self._refresh(stream_id)
            return self._status()

    def arm(self, token, stream_id, timeout_s=5.0):
        if type(token) is not int or not 1 <= token <= 0xffffffff:
            raise CaptureError(400, 'token must be a nonzero uint32')
        if type(timeout_s) not in (int, float) or not 0 < timeout_s <= self.max_wait_s:
            raise CaptureError(400, 'timeout_s must be positive and at most %s' % self.max_wait_s)
        with self.lock:
            self._refresh(stream_id)
            if self.state in ('waiting', 'copying', 'ready'):
                raise CaptureError(409, 'cancel or consume the previous diagnostic before arming')
            self.generation += 1
            self.token = token
            self.frame = self.meta = None
            self.candidates = self.prefix_misses = 0
            self.state, self.error = 'waiting', None
            self.deadline = self.clock() + timeout_s
            return self._status()

    def cancel(self, generation, stream_id):
        with self.lock:
            self._refresh(stream_id)
            if type(generation) is not int or generation != self.generation:
                raise CaptureError(409, 'stale diagnostic generation')
            self._discard('cancelled')
            return self._status()

    def get_frame(self, generation, stream_id):
        with self.lock:
            self._refresh(stream_id)
            if type(generation) is not int or generation != self.generation:
                raise CaptureError(409, 'stale diagnostic generation')
            if self.state != 'ready':
                raise CaptureError(425 if self.state in ('waiting', 'copying') else 410,
                                   'diagnostic frame unavailable: ' + self.state)
            return self.frame, dict(self.meta)

    def observe(self, size, read_prefix, read_frame, meta):
        """Cheap prefix check while armed; the full frame is copied only on match.

        Readers run outside our lock. A concurrent cancel/re-arm cannot publish
        an old copy. The caller's ordinary raw/preview locks must NOT be held.
        Exceptions are confined to diagnostics so preview remains operational.
        """
        stream_id = meta['stream_id']
        with self.lock:
            self._refresh(stream_id)
            if self.state != 'waiting':
                return False
            generation, token = self.generation, self.token
            self.candidates += 1
        try:
            if size != self.expected_bytes:
                return False
            prefix = read_prefix()
            if len(prefix) != 12:
                return False
            magic, received_token, fpga_frame_id = struct.unpack('<III', prefix)
            if magic != MAGIC or received_token != token:
                with self.lock:
                    if self.generation == generation and self.state == 'waiting':
                        self.prefix_misses += 1
                return False
            with self.lock:
                self._refresh(stream_id)
                if self.generation != generation or self.state != 'waiting':
                    return False
                self.state = 'copying'
            started = self.clock()
            data = bytes(read_frame())
            if len(data) != self.expected_bytes or data[:12] != prefix:
                raise ValueError('full frame length or marker changed while copying')
            ppm = self.header + data
            metadata = dict(meta, diagnostic_token=token, fpga_frame_id=fpga_frame_id,
                            diagnostic_generation=generation,
                            diagnostic_copy_ms=(self.clock()-started)*1000,
                            rgb_byte_order='RGB', coordinate_space='native_unrotated',
                            marker_excluded_pixels=[0, 1, 2, 3])
            with self.lock:
                self._refresh(stream_id)
                if self.generation != generation or self.state != 'copying':
                    return False
                self.frame, self.meta = ppm, metadata
                self.state = 'ready'
                self.deadline = self.clock() + self.retention_s
                return True
        except Exception as exc:
            with self.lock:
                if self.generation == generation and self.state in ('waiting', 'copying'):
                    self._discard('error', 'capture_failed:' + type(exc).__name__)
            return False

    def observe_gst_buffer(self, buffer, meta):
        return self.observe(buffer.get_size(), lambda: buffer.extract_dup(0, 12),
                            lambda: buffer.extract_dup(0, self.expected_bytes), meta)


def _json_response(handler, status, obj):
    data = json.dumps(obj, allow_nan=False).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Content-Length', str(len(data)))
    handler.send_header('Cache-Control', 'no-store')
    handler.end_headers()
    handler.wfile.write(data)


def diagnostic_get(handler, capture, stream_id):
    """Return True if the request belongs to the diagnostic API."""
    parsed = urlsplit(handler.path)
    if not parsed.path.startswith(PREFIX):
        return False
    try:
        if parsed.path == PREFIX + 'status':
            _json_response(handler, 200, capture.status(stream_id))
        elif parsed.path == PREFIX + 'frame':
            try:
                values = parse_qs(parsed.query, strict_parsing=True)
                if set(values) != {'generation'} or len(values['generation']) != 1:
                    raise ValueError()
                generation = int(values['generation'][0])
            except (KeyError, ValueError):
                raise CaptureError(400, 'one integer generation query parameter required')
            data, meta = capture.get_frame(generation, stream_id)
            handler.send_response(200)
            handler.send_header('Content-Type', 'image/x-portable-pixmap')
            handler.send_header('Content-Length', str(len(data)))
            handler.send_header('Cache-Control', 'no-store')
            for key, value in {'X-ROI-Generation': generation,
                               'X-ROI-Token': meta['diagnostic_token'],
                               'X-FPGA-Frame-ID': meta['fpga_frame_id'],
                               'X-Raw-Sequence': meta['sequence'],
                               'X-Raw-Stream': meta['stream_id'],
                               'X-Raw-PTS-Ns': meta.get('pts_ns')}.items():
                handler.send_header(key, str(value))
            handler.end_headers()
            handler.wfile.write(data)
        else:
            raise CaptureError(404, 'unknown diagnostic endpoint')
    except CaptureError as exc:
        _json_response(handler, exc.status, {'error': str(exc)})
    except (BrokenPipeError, ConnectionResetError):
        pass
    return True


def diagnostic_post(handler, capture, stream_id):
    parsed = urlsplit(handler.path)
    if not parsed.path.startswith(PREFIX):
        return False
    try:
        try:
            length = int(handler.headers.get('Content-Length', '0'))
        except ValueError:
            raise CaptureError(400, 'invalid Content-Length')
        if length < 1 or length > 1024:
            raise CaptureError(400, 'JSON request must contain 1 to 1024 bytes')
        try:
            obj = json.loads(handler.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            raise CaptureError(400, 'invalid JSON')
        if type(obj) is not dict:
            raise CaptureError(400, 'JSON object required')
        if parsed.path == PREFIX + 'arm':
            if set(obj) - {'token', 'timeout_s'} or 'token' not in obj:
                raise CaptureError(400, 'arm requires token and optional timeout_s')
            result = capture.arm(obj['token'], stream_id, obj.get('timeout_s', 5.0))
        elif parsed.path == PREFIX + 'cancel':
            if set(obj) != {'generation'}:
                raise CaptureError(400, 'cancel requires generation')
            result = capture.cancel(obj['generation'], stream_id)
        else:
            raise CaptureError(404, 'unknown diagnostic endpoint')
        _json_response(handler, 200, result)
    except CaptureError as exc:
        _json_response(handler, exc.status, {'error': str(exc)})
    except (BrokenPipeError, ConnectionResetError):
        pass
    return True
