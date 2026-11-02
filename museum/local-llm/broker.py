"""Local UNIX-only RKLLM supervisor. No network/model fallback; unload per request."""
import fcntl
import http.server
import json
import os
from pathlib import Path
import signal
import socket
import socketserver
import subprocess
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parent
SOCKET = '/run/scan3d-chat/chat.sock'
PRIORITY = '/run/lock/scan3d-chat-priority.lock'
HARDWARE = '/run/lock/afc03-fpga-scan.lock'
MODEL = ROOT/'model/qwen2-0.5b-instruct-rk3576-w4a16.rkllm'
MIN_START_MIB = 1600
MIN_RUN_MIB = 900


def available_mib():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) // 1024
    return 0


def swap_enabled():
    return any(line.startswith('SwapTotal:') and int(line.split()[1]) > 0
               for line in Path('/proc/meminfo').read_text().splitlines())


def locked(path):
    try:
        with open(path, 'r') as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
        return False
    except OSError:
        return True  # missing coordination file is not permission to run


class Engine:
    def __init__(self):
        self.mutex = threading.RLock()
        self.proc = None
        self.request_id = None
        self.reason = ''
        self.last = None
        self.cancelled = {}

    def stop(self, reason, identifier=None):
        with self.mutex:
            if identifier is not None:
                self.cancelled[identifier] = time.monotonic()
            if identifier is not None and identifier != self.request_id:
                return
            self.reason = reason
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait(timeout=2)

    def status(self):
        with self.mutex:
            busy = locked(PRIORITY) or locked(HARDWARE)
            memory = available_mib()
            return dict(configured=MODEL.is_file() and (ROOT/'qwen-worker').is_file(),
                        model='Qwen2-0.5B-Instruct', backend='RKLLM W4A16 / RK3576 NPU',
                        running=self.request_id is not None, scan_busy=busy,
                        available_mib=memory, min_available_mib=MIN_START_MIB,
                        admission=not busy and memory >= MIN_START_MIB and not swap_enabled(),
                        swap_enabled=swap_enabled(),
                        vision=False, cloud_fallback=False, last=self.last)

    def run(self, body):
        prompt = body.get('prompt', '')
        identifier = body.get('id', '')
        if not isinstance(prompt, str) or not 1 <= len(prompt.encode()) <= 3200:
            return 400, dict(error='对话上下文过长，请缩短档案或问题')
        if not isinstance(identifier, str) or len(identifier) != 36:
            return 400, dict(error='无效请求编号')
        with tempfile.TemporaryDirectory(prefix='qwen-', dir='/run/scan3d-chat') as tmp:
            tmp = Path(tmp)
            (tmp/'prompt').write_text(prompt, encoding='utf-8')
            started = time.monotonic()
            with (tmp/'log').open('w+b') as log:
                with self.mutex:
                    self.cancelled = {k: v for k, v in self.cancelled.items() if time.monotonic()-v < 60}
                    if identifier in self.cancelled:
                        return 409, dict(error='回答已取消')
                    if self.request_id is not None:
                        return 429, dict(error='本地模型正在回答，请稍后再试')
                    if locked(PRIORITY) or locked(HARDWARE):
                        return 409, dict(error='扫描或点云处理优先，聊天暂时暂停')
                    if available_mib() < MIN_START_MIB:
                        return 503, dict(error='可用内存不足，暂不加载聊天模型')
                    if swap_enabled():
                        return 503, dict(error='本地聊天要求禁用交换内存，当前拒绝加载模型')
                    if not MODEL.is_file():
                        return 503, dict(error='本地 Qwen 模型未安装')
                    self.reason = ''
                    self.request_id = identifier
                    try:
                        self.proc = subprocess.Popen([str(ROOT/'qwen-worker'), str(MODEL),
                                                      str(tmp/'prompt'), str(tmp/'answer')],
                                                     stdout=log, stderr=log)
                    except Exception:
                        self.request_id = None
                        self.proc = None
                        raise
                peak_rss = 0
                low_memory = available_mib()
                try:
                    while self.proc.poll() is None:
                        memory = available_mib()
                        low_memory = min(low_memory, memory)
                        rss = 0
                        try:
                            fields = Path('/proc/%s/status' % self.proc.pid).read_text().splitlines()
                            rss = next(int(x.split()[1]) for x in fields if x.startswith('VmRSS:'))
                            peak_rss = max(peak_rss, rss)
                        except (OSError, StopIteration):
                            pass
                        # Serialize lock probes with status/admission probes. Otherwise
                        # one probe's momentary EX lock can look like a real scanner.
                        with self.mutex:
                            resource_busy = locked(PRIORITY) or locked(HARDWARE)
                        if resource_busy:
                            self.stop('扫描或点云处理优先，已停止本次聊天')
                        elif memory < MIN_RUN_MIB:
                            self.stop('可用内存降低，已释放聊天模型')
                        elif rss > 768*1024 or swap_enabled():
                            self.stop('聊天资源超出限制，已释放模型')
                        elif time.monotonic()-started > 45:
                            self.stop('本地模型回答超时，请缩短问题')
                        time.sleep(.05)
                    log.seek(0)
                    logs = log.read().decode(errors='replace')
                    metrics = dict(elapsed_ms=round((time.monotonic()-started)*1000),
                                   peak_rss_kib=peak_rss, min_available_mib=low_memory,
                                   exit_code=self.proc.returncode)
                    for line in logs.splitlines():
                        if line.startswith('SCAN3D_PERF '):
                            metrics.update(json.loads(line[12:]))
                    self.last = metrics
                    # Do not log prompts, answers, or raw model logs (which may contain prompts).
                    print(json.dumps(dict(event='inference', **metrics)), flush=True)
                    if self.reason:
                        return 409, dict(error=self.reason)
                    if self.proc.returncode != 0:
                        return 503, dict(error='本地 NPU 推理失败，未调用其他模型')
                    answer = (tmp/'answer').read_text(encoding='utf-8').strip()
                    if not answer:
                        return 502, dict(error='本地模型未生成有效回答')
                    return 200, dict(text=answer[:1600], model='Qwen2-0.5B-Instruct',
                                     source='Qwen2 本地 NPU', metrics=metrics)
                finally:
                    with self.mutex:
                        if self.proc and self.proc.poll() is None:
                            self.stop('请求结束')
                        self.proc = None
                        self.request_id = None


engine = Engine()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, data):
        raw = json.dumps(data, ensure_ascii=False).encode()
        try:
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        self.reply(200, engine.status()) if self.path == '/status' else self.reply(404, {})

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 12000:
                return self.reply(413, dict(error='请求过长'))
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                return self.reply(400, {})
            if self.path == '/preempt':
                engine.stop('扫描或点云处理优先，已停止本次聊天')
                return self.reply(200, dict(released=True))
            if self.path == '/cancel':
                engine.stop('回答已取消', body.get('id'))
                return self.reply(200, dict(cancelled=True))
            if self.path == '/chat':
                return self.reply(*engine.run(body))
            self.reply(404, {})
        except Exception:
            self.reply(500, dict(error='本地推理服务异常'))


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


if __name__ == '__main__':
    Path(SOCKET).unlink(missing_ok=True)
    with Server(SOCKET, Handler) as server:
        os.chmod(SOCKET, 0o660)
        def stop(*_):
            engine.stop('服务停止')
            os._exit(0)
        signal.signal(signal.SIGTERM, stop)
        server.serve_forever(poll_interval=.1)
