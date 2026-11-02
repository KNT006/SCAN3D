"""Persistent serial transport configured for the installed hardware module.

Each operation defines a wire template and a full-line reply expression with
named groups. State fields come from replies, never from transmitted requests.
"""
import json
import re
import time
from pathlib import Path

OPERATIONS = {"ping", "position", "state", "enable", "disable", "enabled",
              "stop", "move", "arm", "disarm", "zero", "pulse_move",
              "laser", "laser_state", "laser_keep", "led", "led_state"}


class SerialModule:
    def __init__(self, profile_path, transport=None):
        profile = json.loads(Path(profile_path).read_text(encoding="utf-8"))
        self.operations = profile["operations"]
        missing = OPERATIONS - self.operations.keys()
        if missing:
            raise ValueError("Missing module operations: " + ", ".join(sorted(missing)))
        self.timeout = float(profile.get("reply_timeout_seconds", 2))
        if not 0 < self.timeout <= 3:
            raise ValueError("Reply timeout must be in (0, 3] seconds")
        self.encoding = profile.get("encoding", "ascii")
        for operation, spec in self.operations.items():
            if not isinstance(spec.get("request"), str) or not spec["request"]:
                raise ValueError("Missing request template: " + operation)
            pattern = re.compile(spec["response"])
            required = {
                "ping": {"ready"}, "position": {"deg"},
                "state": {"session", "emitted", "moving", "pending", "count_known", "armed", "fault"},
                "enabled": {"enabled"}, "laser_state": {"A", "B", "remaining_ms"}, "led_state": {"white"},
            }.get(operation, {"accepted"})
            if required - pattern.groupindex.keys():
                raise ValueError("Missing reply fields: " + operation)
        if transport is None:
            import serial
            transport = serial.Serial(port=None, baudrate=int(profile["baudrate"]),
                                      timeout=0.05, write_timeout=1,
                                      rtscts=False, dsrdtr=False, exclusive=True)
            transport.dtr = bool(profile.get("dtr", False))
            transport.rts = bool(profile.get("rts", False))
            transport.port = profile["device"]
            transport.open()
        self.transport = transport
        self.failed = False

    def dispatch(self, operation, arguments):
        if self.failed:
            raise RuntimeError("Module connection uncertain; restart after checking hardware")
        spec = self.operations[operation]
        wire = spec["request"].format_map(arguments).encode(self.encoding)
        if len(wire) > 512:
            raise ValueError("Module request exceeds 512 bytes")
        try:
            # Discard stale replies before dispatch, never retry a dispatched command.
            self.transport.reset_input_buffer()
            written = self.transport.write(wire)
            if written != len(wire):
                raise OSError("Incomplete module request")
            self.transport.flush()
            deadline = time.monotonic() + self.timeout
            pending = bytearray()
            while time.monotonic() < deadline:
                chunk = self.transport.read(1)
                if not chunk:
                    continue
                pending.extend(chunk)
                if len(pending) > 4096:
                    raise OSError("Module reply exceeds 4096 bytes")
                if chunk == b"\n":
                    line = pending.decode(self.encoding).rstrip("\r\n")
                    match = re.fullmatch(spec["response"], line)
                    if match is None:
                        raise OSError("Unexpected module reply for " + operation)
                    return match.groupdict()
            raise TimeoutError("Module reply timeout; command will not be repeated")
        except BaseException:
            self.failed = True
            raise

    def close(self):
        self.transport.close()
