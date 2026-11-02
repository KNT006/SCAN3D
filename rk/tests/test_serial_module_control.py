import importlib.util
import ast
import re
from types import SimpleNamespace
import json
import sys
import socket
import threading
import time
import tempfile
import unittest
from pathlib import Path

MOTOR = Path(__file__).resolve().parents[1] / "rootfs/opt/afc03-motor"
sys.path.insert(0, str(MOTOR))
from control_api import ControlAPI
from serial_module import OPERATIONS, SerialModule


class FakeSerial:
    def __init__(self, reply=b"ACK 1\n"):
        self.reply = bytearray(reply)
        self.writes = []
    def reset_input_buffer(self): pass
    def write(self, data):
        self.writes.append(data)
        return len(data)
    def flush(self): pass
    def read(self, count):
        result = bytes(self.reply[:count])
        del self.reply[:count]
        return result
    def close(self): pass


class FakeModule:
    def __init__(self, response):
        self.response = response
        self.calls = []
    def dispatch(self, operation, arguments):
        self.calls.append((operation, arguments))
        return self.response


class ControlTests(unittest.TestCase):
    def test_state_requires_all_feedback(self):
        api = ControlAPI(FakeModule({"session": "1", "emitted": "20"}))
        with self.assertRaises(KeyError): api.execute("PULSE_STATE")

    def test_state_preserves_unknown_count(self):
        reply = dict(session="4", emitted="-16", moving="0", pending="0",
                     count_known="0", armed="0", fault="stopped")
        result = ControlAPI(FakeModule(reply)).execute("PULSE_STATE")
        self.assertIn("count_known=0", result)
        self.assertIn("emitted=-16", result)

    def test_move_ack_does_not_claim_completion(self):
        module = FakeModule({"accepted": "1"})
        result = ControlAPI(module).execute("PULSE_MOVE -53 40 7")
        self.assertEqual(module.calls, [("pulse_move", dict(pulses=-53, rate=40, session=7))])
        self.assertEqual(result, "OK PULSE_MOVE accepted=1")

    def test_rejected_move(self):
        with self.assertRaises(RuntimeError):
            ControlAPI(FakeModule({"accepted": "0"})).execute("MOVE 20 10")

    def test_invalid_commands_do_not_dispatch(self):
        module = FakeModule({"accepted": "1"})
        for command in ("MOVE 0 10", "LED 33", "LASER C", "PULSE_MOVE 3201 40 7", "STOP extra"):
            with self.assertRaises(ValueError): ControlAPI(module).execute(command)
        self.assertEqual(module.calls, [])


    def test_client_timeout_closes_without_retry(self):
        from rk_motor import MotorBridge
        class Socket:
            writes, closed = 0, False
            def sendall(self, data): self.writes += 1
            def recv(self, count): raise TimeoutError("test timeout")
            def close(self): self.closed = True
        bridge = MotorBridge.__new__(MotorBridge)
        bridge.proxy = Socket()
        with self.assertRaises(TimeoutError): bridge.send("PULSE_MOVE 53 40 1")
        self.assertEqual(bridge.proxy.writes, 1)
        self.assertTrue(bridge.proxy.closed)

    def test_enabled_response_matches_existing_capture_check(self):
        for enabled in (0, 1):
            response = ControlAPI(FakeModule({"enabled": str(enabled)})).execute("ENSTATE")
            self.assertEqual(response == "OK ENSTATE 1", enabled == 1)

    def test_position_consumed_by_existing_scan(self):
        source = MOTOR.parent / "afc03-scanner/backend/live_worker.py"
        tree = ast.parse(source.read_text(encoding="utf8"))
        scan = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Scan")
        method = next(node for node in scan.body if isinstance(node, ast.FunctionDef) and node.name == "pos")
        method.decorator_list = []
        namespace = {"re": re}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"), namespace)
        api = ControlAPI(FakeModule({"deg": "-12.375"}))
        observed = []
        worker = SimpleNamespace(send=api.execute, update=lambda **fields: observed.append(fields))
        self.assertEqual(namespace["pos"](worker), -12.375)

    def test_led_applied_value_matches_capture_consumer(self):
        source = MOTOR.parent / "afc03-scanner/backend/live_worker.py"
        tree = ast.parse(source.read_text(encoding="utf8"))
        predicate = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "light_matches")
        namespace = {"re": re}
        exec(compile(ast.Module(body=[predicate], type_ignores=[]), str(source), "exec"), namespace)
        module = FakeModule({"accepted": "1", "white": "8"})
        response = ControlAPI(module).execute("LED 8")
        self.assertTrue(namespace["light_matches"](response, 8))
        self.assertEqual(module.calls, [("led", {"white": 8}), ("led_state", {})])
        with self.assertRaises(RuntimeError):
            ControlAPI(FakeModule({"accepted": "1", "white": "3"})).execute("LED 8")

    def test_manual_laser_preserves_other_channel_and_lease(self):
        source = MOTOR.parent / "afc03-scanner/scan3d/manual_laser.py"
        spec = importlib.util.spec_from_file_location("consumer_manual_laser", source)
        consumer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(consumer)
        class Hardware:
            A, B, remaining_ms = "1", "0", "2000"
            calls = []
            def dispatch(self, operation, arguments):
                self.calls.append((operation, arguments))
                if operation == "laser_state":
                    return dict(A=self.A, B=self.B, remaining_ms=self.remaining_ms)
                if operation == "laser":
                    self.A = str(int(arguments["channel"] in ("A", "BOTH")))
                    self.B = str(int(arguments["channel"] in ("B", "BOTH")))
                return {"accepted": "1"}
        hardware = Hardware()
        manual = consumer.ManualLaser(ControlAPI(hardware).execute)
        manual.lights(laser_b=True)
        self.assertEqual(manual.status()["channel"], "AB")
        self.assertIn(("laser", {"channel": "BOTH"}), hardware.calls)
        manual.renew()
        self.assertEqual(hardware.calls[-1], ("laser_keep", {}))
        hardware.remaining_ms = "0"
        manual.renew()
        self.assertEqual(manual.status()["channel"], "OFF")
        self.assertEqual(hardware.calls[-1][0], "laser_state")

    def test_laser_state_requires_real_lease_feedback(self):
        with self.assertRaises(KeyError):
            ControlAPI(FakeModule({"A": "1", "B": "0"})).execute("LASERSTATE")

    def profile(self, path, operations=None):
        path.write_text(json.dumps(dict(reply_timeout_seconds=.01, operations=operations or {
            operation: dict(request="TEST {pulses}\n" if operation == "pulse_move" else "TEST\n",
                            response=(r"ACK (?P<accepted>[01])" if operation not in {
                                "ping", "position", "state", "enabled", "laser_state", "led_state"
                            } else " ".join("(?P<" + field + ">.+)" for field in {
                                "ping": ["ready"], "position": ["deg"],
                                "state": ["session", "emitted", "moving", "pending", "count_known", "armed", "fault"],
                                "enabled": ["enabled"], "laser_state": ["A", "B", "remaining_ms"], "led_state": ["white"]
                            }[operation]))) for operation in OPERATIONS})))

    def test_serial_maps_configured_protocol(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            self.profile(path)
            serial = FakeSerial()
            module = SerialModule(path, serial)
            self.assertEqual(module.dispatch("pulse_move", {"pulses": 53}), {"accepted": "1"})
            self.assertEqual(serial.writes, [b"TEST 53\n"])

    def test_timeout_never_replays(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            self.profile(path)
            serial = FakeSerial(b"")
            module = SerialModule(path, serial)
            with self.assertRaises(TimeoutError): module.dispatch("stop", {})
            with self.assertRaises(RuntimeError): module.dispatch("stop", {})
            self.assertEqual(len(serial.writes), 1)

    def test_incomplete_profile_rejected_before_open(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            self.profile(path, {"ping": {}})
            with self.assertRaises(ValueError): SerialModule(path)

    def test_unexpected_reply_invalidates_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            self.profile(path)
            module = SerialModule(path, FakeSerial(b"GARBAGE\n"))
            with self.assertRaises(OSError): module.dispatch("stop", {})
            self.assertTrue(module.failed)


class BrokerTests(unittest.TestCase):
    def setUp(self):
        source = MOTOR.parents[1] / "root/deploy/controller-20261002/controllerd.py"
        spec = importlib.util.spec_from_file_location("test_controllerd", source)
        broker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(broker)
        self.server_class = broker.ControlServer
        self.servers = []
        self.connections = []

    def tearDown(self):
        for connection in self.connections:
            connection.close()
        for server in self.servers:
            server.close()

    def connect(self, server):
        client, peer = socket.socketpair()
        client.settimeout(1)
        self.connections.append(client)
        server.start_client(peer)
        return client, self.receive(client)

    @staticmethod
    def receive(client):
        data = bytearray()
        while True:
            value = client.recv(1)
            if value == b"\n":
                return json.loads(data)
            if not value:
                raise RuntimeError("Disconnected")
            data.extend(value)

    @staticmethod
    def send(client, command):
        client.sendall(json.dumps({"command": command}).encode() + b"\n")

    def test_idle_client_does_not_block_second_client_ping_and_stop(self):
        module = FakeModule({"ready": "1", "accepted": "1"})
        server = self.server_class(ControlAPI(module))
        self.servers.append(server)
        idle, hello = self.connect(server)
        self.assertTrue(hello["connected"])
        active, hello = self.connect(server)
        self.assertTrue(hello["connected"])
        self.send(active, "PING")
        self.assertEqual(self.receive(active), {"reply": "OK rk_control_v1"})
        self.send(active, "STOP")
        self.assertEqual(self.receive(active), {"reply": "OK STOP accepted=1"})
        self.assertEqual(module.calls, [("ping", {}), ("stop", {})])

    def test_busy_command_is_rejected_without_later_dispatch(self):
        started, release = threading.Event(), threading.Event()
        class SlowModule(FakeModule):
            def dispatch(self, operation, arguments):
                self.calls.append((operation, arguments))
                if operation == "ping":
                    started.set()
                    release.wait(2)
                return {"ready": "1", "accepted": "1"}
        module = SlowModule({})
        server = self.server_class(ControlAPI(module))
        self.servers.append(server)
        first, _ = self.connect(server)
        second, _ = self.connect(server)
        try:
            self.send(first, "PING")
            self.assertTrue(started.wait(1))
            self.send(second, "PULSE_MOVE 53 40 1")
            self.assertIn("not dispatched", self.receive(second)["error"])
        finally:
            release.set()
        self.assertEqual(self.receive(first), {"reply": "OK rk_control_v1"})
        self.send(second, "STOP")
        self.assertEqual(self.receive(second), {"reply": "OK STOP accepted=1"})
        self.assertEqual(module.calls, [("ping", {}), ("stop", {})])

    def test_client_limit_rejects_without_command(self):
        module = FakeModule({"ready": "1"})
        server = self.server_class(ControlAPI(module), max_clients=1)
        self.servers.append(server)
        first, hello = self.connect(server)
        self.assertTrue(hello["connected"])
        second, hello = self.connect(server)
        self.assertFalse(hello["connected"])
        self.assertEqual(module.calls, [])


if __name__ == "__main__": unittest.main()
