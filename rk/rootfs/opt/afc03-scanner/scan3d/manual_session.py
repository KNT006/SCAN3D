"""Share one broker connection during manual motion; serialize whole request/reply pairs."""
import threading


class ManualSession:
    def __init__(self, factory):
        self.factory = factory
        self.lock = threading.RLock()
        self.bridge = None

    def open(self):
        with self.lock:
            if self.bridge is not None:
                raise ValueError('手动转动正在执行')
            self.bridge = self.factory()

    def send(self, command):
        with self.lock:
            if self.bridge is not None:
                return self.bridge.send(command)
            bridge = self.factory()
            try:
                return bridge.send(command)
            finally:
                bridge.close()

    def close(self):
        with self.lock:
            bridge, self.bridge = self.bridge, None
            if bridge is not None:
                bridge.close()
