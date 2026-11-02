"""Manual continuous laser mode; renew existing lease, never relight on retry."""
import re
import threading


class ManualLaser:
    def __init__(self, send):
        self.send = send
        self.lock = threading.RLock()
        self.channel = 'OFF'
        self.led = 0
        self.error = ''

    def status(self):
        with self.lock:
            return dict(channel=self.channel, led=self.led, continuous=self.channel != 'OFF', error=self.error)

    def clear(self, off=False):
        with self.lock:
            self.channel = 'OFF'
            self.error = ''
            if off:
                self._send('LASER OFF')

    def _send(self, command):
        reply = self.send(command)
        if not reply.startswith('OK '):
            raise ValueError(reply)
        return reply

    def lights(self, channel=None, led=None, laser_a=None, laser_b=None):
        with self.lock:
            if channel is not None and channel not in ('OFF', 'A', 'B', 'AB'):
                raise ValueError('无效激光通道')
            if led is not None and (type(led) is not int or not 0 <= led <= 32):
                raise ValueError('灯光亮度必须为 0～32 的整数')
            if any(v is not None and type(v) is not bool for v in (laser_a, laser_b)):
                raise ValueError('激光开关参数必须为布尔值')
            if channel is not None and (laser_a is not None or laser_b is not None):
                raise ValueError('不能同时指定激光通道和独立开关')
            if all(v is None for v in (channel, led, laser_a, laser_b)):
                raise ValueError('未指定光源操作')
            if laser_a is not None or laser_b is not None:
                # Preserve the controller's actual commanded mask, not a stale UI
                # state after a lease expiry/reboot. This is not optical feedback.
                fields = dict(re.findall(r'(?<!\S)(A|B|remaining_ms)=(\d+)(?!\S)', self._send('LASERSTATE')))
                if fields.get('A') not in ('0','1') or fields.get('B') not in ('0','1') or 'remaining_ms' not in fields:
                    raise ValueError('无法读取激光开关状态，请检查控制器')
                live = int(fields['remaining_ms']) > 0
                a = laser_a if laser_a is not None else live and fields['A'] == '1'
                b = laser_b if laser_b is not None else live and fields['B'] == '1'
                channel = ('A' if a else '') + ('B' if b else '') or 'OFF'
            replies = {}
            try:
                if channel is not None:
                    replies['laser'] = self._send('LASER ' + ('BOTH' if channel == 'AB' else channel))
                    self.channel = channel
                    self.error = ''
                if led is not None:
                    replies['led'] = self._send('LED ' + str(led))
                    self.led = led
                return dict(**replies, manual_laser=self.status())
            except Exception:
                # A failed laser operation must not leave a renewed laser on.
                if channel is not None:
                    self.channel = 'OFF'
                    try:self._send('LASER OFF')
                    except Exception:pass
                if led is not None:
                    self.led = None  # Unknown after a lost acknowledgement.
                raise

    def renew(self):
        with self.lock:
            if self.channel == 'OFF':
                return
            try:
                reply = self._send('LASERSTATE')
                fields = dict(re.findall(r'(?<!\S)(A|B|remaining_ms)=(\d+)(?!\S)', reply))
                expected = {'A':('1','0'), 'B':('0','1'), 'AB':('1','1')}[self.channel]
                if (fields.get('A'), fields.get('B')) != expected or int(fields.get('remaining_ms', '0')) <= 0:
                    raise ValueError('控制器激光状态已改变，常亮已取消')
                self._send('LASERKEEP')
            except Exception as exc:
                # No LASER A/B retry: reboot, timeout and external OFF remain OFF.
                self.channel = 'OFF'
                self.error = str(exc)
