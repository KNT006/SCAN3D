"""Exclusive local broker for RK serial hardware control."""
import json
import os
import signal
import socket
import sys
import threading
from pathlib import Path

sys.path.insert(0, "/opt/afc03-motor")
from control_api import ControlAPI
from serial_module import SerialModule

PATH = "/run/afc03-controller/control.sock"


def serve_client(conn, api, command_lock, stopping):
    conn.settimeout(1)
    try:
        conn.sendall(b'{"connected":true}\n')
    except (ConnectionError, socket.timeout):
        return
    pending = bytearray()
    while not stopping.is_set():
        try:
            data = conn.recv(512)
        except socket.timeout:
            continue
        except ConnectionError:
            return
        if not data:
            return
        pending.extend(data)
        if len(pending) > 4096:
            return
        while b"\n" in pending:
            line, _, remainder = pending.partition(b"\n")
            pending = bytearray(remainder)
            fatal = None
            try:
                command = json.loads(line)["command"]
                if not isinstance(command, str) or not command or len(command) > 110:
                    raise ValueError("Invalid command")
                if any(ord(char) < 32 or ord(char) > 126 for char in command):
                    raise ValueError("Invalid command character")
                if not command_lock.acquire(timeout=0.1):
                    raise RuntimeError("Hardware module busy; command not dispatched")
                try:
                    if stopping.is_set():
                        raise RuntimeError("Control service stopping; command not dispatched")
                    response = {"reply": api.execute(command)}
                finally:
                    command_lock.release()
            except OSError as exc:
                fatal = exc
                response = {"error": str(exc) + "; command will not be repeated"}
            except (ValueError, KeyError, RuntimeError) as exc:
                response = {"error": str(exc)}
            try:
                conn.sendall(json.dumps(response).encode() + b"\n")
            except (ConnectionError, socket.timeout):
                if fatal is not None:
                    raise fatal
                return
            if fatal is not None:
                raise fatal



class ControlServer:
    def __init__(self, api, max_clients=8):
        self.api = api
        self.command_lock = threading.Lock()
        self.stopping = threading.Event()
        self.slots = threading.BoundedSemaphore(max_clients)
        self.clients = {}
        self.clients_lock = threading.Lock()

    def start_client(self, conn):
        if self.stopping.is_set() or not self.slots.acquire(blocking=False):
            try:
                conn.settimeout(0.1)
                conn.sendall(b'{"connected":false,"error":"Control service busy"}\n')
            except OSError:
                pass
            finally:
                conn.close()
            return False
        thread = threading.Thread(target=self._client, args=(conn,), daemon=True)
        with self.clients_lock:
            self.clients[thread] = conn
        thread.start()
        return True

    def _client(self, conn):
        try:
            with conn:
                serve_client(conn, self.api, self.command_lock, self.stopping)
        except OSError as exc:
            print(f"Control connection: {exc}", file=sys.stderr)
        finally:
            with self.clients_lock:
                self.clients.pop(threading.current_thread(), None)
            self.slots.release()

    def close(self):
        self.stopping.set()
        with self.clients_lock:
            clients = list(self.clients.items())
        for _, conn in clients:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        for thread, _ in clients:
            thread.join(timeout=4)


def main():
    def stop_service(*_):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop_service)
    profile = os.environ.get("AFC03_MODULE_PROFILE", "/etc/afc03-control/module.json")
    module = SerialModule(profile)
    api = ControlAPI(module)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    clients = ControlServer(api)
    try:
        api.execute("PING")
        api.execute("PULSE_STATE")
        path = Path(PATH)
        if path.exists():
            if not path.is_socket():
                raise RuntimeError("Control socket path is not a socket")
            path.unlink()
        server.bind(PATH)
        os.chmod(PATH, 0o660)
        server.listen(4)
        while True:
            conn, _ = server.accept()
            clients.start_client(conn)
    finally:
        clients.close()
        # Best effort only: an unavailable module must never report successful stop.
        if clients.command_lock.acquire(timeout=4):
            try:
                for command in ("STOP", "LASER OFF", "LED 0", "DISABLE"):
                    try:
                        api.execute(command)
                    except Exception as exc:
                        print(f"Shutdown {command}: {exc}", file=sys.stderr)
            finally:
                clients.command_lock.release()
        else:
            print("Hardware transaction still active; shutdown outputs unconfirmed", file=sys.stderr)
        module.close()
        server.close()


if __name__ == "__main__":
    main()
