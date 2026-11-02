"""Local command compatibility boundary; hardware uses structured operations."""
import math
from decimal import Decimal

QUERIES = {"PING": "ping", "POS": "position", "PULSE_STATE": "state",
           "ENSTATE": "enabled", "LASERSTATE": "laser_state", "LEDSTATE": "led_state"}
ACTIONS = {"ENABLE": "enable", "DISABLE": "disable", "STOP": "stop",
           "PULSE_DISARM": "disarm", "LASERKEEP": "laser_keep"}
STATE_KEYS = ("session", "emitted", "moving", "pending", "count_known", "armed")


def integer(value, low=None, high=None):
    value = int(value)
    if (low is not None and value < low) or (high is not None and value > high):
        raise ValueError("Control value outside supported range")
    return value


class ControlAPI:
    def __init__(self, module):
        self.module = module

    def execute(self, command):
        words = command.split()
        if not words:
            raise ValueError("Empty command")
        name, args = words[0], words[1:]
        values = {}
        if name in QUERIES or name in ACTIONS:
            if args:
                raise ValueError("Unexpected command arguments")
            operation = (QUERIES | ACTIONS)[name]
        elif name in ("PULSE_ARM", "PULSE_ZERO") and len(args) == 1:
            operation = "arm" if name == "PULSE_ARM" else "zero"
            values = {"session": integer(args[0], 0)}
        elif name == "PULSE_MOVE" and len(args) == 3:
            operation = "pulse_move"
            values = {"pulses": integer(args[0], -3200, 3200),
                      "rate": integer(args[1], 1), "session": integer(args[2], 0)}
            if not values["pulses"]:
                raise ValueError("Zero pulse move")
        elif name == "MOVE" and len(args) == 2:
            operation = "move"
            values = {"pulses": integer(args[0], -3200, 3200),
                      "speed": integer(args[1], 1, 100)}
            if not values["pulses"]:
                raise ValueError("Zero pulse move")
        elif name == "LASER" and len(args) == 1 and args[0] in ("OFF", "A", "B", "BOTH"):
            operation, values = "laser", {"channel": args[0]}
        elif name == "LED" and len(args) == 1:
            operation, values = "led", {"white": integer(args[0], 0, 32)}
        else:
            raise ValueError("Unsupported control command")
        reply = self.module.dispatch(operation, values)
        if name == "PING":
            if reply.get("ready") != "1":
                raise RuntimeError("Hardware module not ready")
            return "OK rk_control_v1"
        if name == "PULSE_STATE":
            fields = {key: integer(reply[key]) for key in STATE_KEYS}
            for key in ("moving", "count_known", "armed"):
                integer(fields[key], 0, 1)
            integer(fields["session"], 0)
            integer(fields["pending"], 0)
            fault = reply["fault"]
            if not fault or any(c.isspace() for c in fault):
                raise ValueError("Invalid fault field")
            return "OK PULSE_STATE " + " ".join(f"{key}={value}" for key, value in fields.items()) + " fault=" + fault
        if name == "POS":
            degree = float(reply["deg"])
            if not math.isfinite(degree):
                raise ValueError("Invalid position")
            return "OK POS deg=" + format(Decimal(str(degree)), "f")
        if name == "ENSTATE":
            return "OK ENSTATE " + str(integer(reply["enabled"], 0, 1))
        if name == "LASERSTATE":
            return (f"OK LASERSTATE A={integer(reply['A'], 0, 1)} B={integer(reply['B'], 0, 1)}"
                    f" remaining_ms={integer(reply['remaining_ms'], 0)}")
        if name == "LEDSTATE":
            return "OK LEDSTATE white=" + str(integer(reply["white"], 0, 32))
        # Acceptance is not completion; callers must poll state and verify counts.
        if reply.get("accepted") != "1":
            raise RuntimeError("Hardware module rejected " + operation)
        if name == "LED":
            # Existing capture consumers verify the applied brightness, not just ACK.
            readback = self.module.dispatch("led_state", {})
            white = integer(readback["white"], 0, 32)
            if white != values["white"]:
                raise RuntimeError("Lighting readback differs from requested brightness")
            return f"OK LED accepted=1 white={white}"
        return "OK " + name + " accepted=1"
