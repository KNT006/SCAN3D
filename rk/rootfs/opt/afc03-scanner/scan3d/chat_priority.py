"""Scanning owns a shared reservation; chat admission requires no reservation."""
from contextlib import contextmanager
import fcntl
from functools import wraps
import http.client
import json
import socket
from pathlib import Path

LOCK = '/run/lock/scan3d-chat-priority.lock'
SOCKET = '/run/scan3d-chat/chat.sock'


@contextmanager
def reserve():
    # An installation without local chat has no lock/socket and remains compatible.
    if not Path(LOCK).exists():
        yield
        return
    with open(LOCK, 'r') as fd:
        fcntl.flock(fd, fcntl.LOCK_SH)
        if Path(SOCKET).exists():
            conn = http.client.HTTPConnection('localhost', timeout=4)
            try:
                conn.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                conn.sock.settimeout(4)
                conn.sock.connect(SOCKET)
                conn.request('POST', '/preempt', '{}', {'Content-Type': 'application/json'})
                response = conn.getresponse()
                if response.status != 200 or not json.loads(response.read()).get('released'):
                    raise RuntimeError('聊天模型尚未释放，请稍后重试')
            except (FileNotFoundError, ConnectionRefusedError):
                pass  # no supervisor listening; systemd KillMode removes its children
            finally:
                conn.close()
        yield


def priority_operation(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with reserve():
            return function(*args, **kwargs)
    return wrapped
