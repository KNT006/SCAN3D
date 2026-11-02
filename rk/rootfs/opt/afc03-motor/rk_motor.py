#!/usr/bin/env python3
"""Client for the RK hardware-control service."""
import argparse
import json
import os
import socket
import sys

DEFAULT_SOCKET = "/run/afc03-controller/control.sock"


class MotorBridge:
    def __init__(self, port=None):
        # The service owns the device; callers retain the existing constructor.
        path = os.environ.get("AFC03_CONTROL_SOCKET", DEFAULT_SOCKET)
        if port and str(port).endswith(".sock"):
            path = str(port)
        self.proxy = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.proxy.settimeout(10)
        try:
            self.proxy.connect(path)
            if self._receive().get("connected") is not True:
                raise RuntimeError("Hardware control service is not ready")
        except BaseException:
            self.proxy.close()
            raise

    def _receive(self):
        data = bytearray()
        while len(data) < 4096:
            chunk = self.proxy.recv(1)
            if not chunk:
                raise RuntimeError("Control connection lost; do not repeat motion")
            if chunk == b"\n":
                return json.loads(data)
            data.extend(chunk)
        raise RuntimeError("Control response exceeds 4096 bytes")

    def close(self):
        self.proxy.close()

    def send(self, command):
        try:
            self.proxy.sendall(json.dumps({"command": command}).encode() + b"\n")
            answer = self._receive()
            if not isinstance(answer, dict) or not ({"reply", "error"} & answer.keys()):
                raise RuntimeError("Invalid control response")
        except (OSError, RuntimeError, ValueError):
            self.proxy.close()
            raise
        if "error" in answer:
            raise RuntimeError(answer["error"])
        return answer["reply"]

    def ping(self):
        return self.send("PING")

    def position(self):
        return self.send("POS")

    def move(self, pulses, speed=20):
        if type(pulses) is not int or not 1 <= abs(pulses) <= 3200:
            raise ValueError("pulses must be a nonzero integer within +/-3200")
        if type(speed) is not int or not 1 <= speed <= 100:
            raise ValueError("speed must be a gear in 1..100, not RPM")
        return self.send(f"MOVE {pulses} {speed}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default=DEFAULT_SOCKET, help="local control socket")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("ping", "pos", "enable", "disable", "enstate", "stop"):
        sub.add_parser(name)
    move = sub.add_parser("move")
    move.add_argument("pulses", type=int)
    move.add_argument("--speed", type=int, default=20)
    args = parser.parse_args()
    bridge = None
    try:
        bridge = MotorBridge(args.port)
        print(bridge.move(args.pulses, args.speed) if args.cmd == "move"
              else bridge.send(args.cmd.upper()))
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if bridge is not None:
            bridge.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
