"""Save/restore preview gain while the caller owns the scanner hardware lock."""
import re
import subprocess
from pathlib import Path


class PreviewGain:
    def __init__(self, device=None, readback=None):
        if device is None:
            nodes = [Path('/dev') / p.parent.name
                     for p in Path('/sys/class/video4linux').glob('video*/name')
                     if 'milianke' in p.read_text().lower()]
            if len(nodes) != 1:
                raise RuntimeError('Cannot uniquely identify FPGA camera')
            device = str(nodes[0])
        self.device = str(device)
        match = re.fullmatch(r'gain:\s*(\d+)\s*', readback if readback is not None else self.read())
        if not match or not 0 <= int(match[1]) <= 240:
            raise RuntimeError('Preview gain is outside the supported 0-240 range')
        self.value = int(match[1])

    def read(self):
        return subprocess.check_output(
            ['v4l2-ctl', '-d', self.device, '--get-ctrl=gain'], text=True, timeout=5).strip()

    def restore(self):
        subprocess.run(['v4l2-ctl', '-d', self.device,
                        '--set-ctrl=gain=' + str(self.value)], check=True, timeout=5)
        readback = self.read()
        if readback != 'gain: ' + str(self.value):
            raise RuntimeError('Preview gain restore readback mismatch: ' + readback)
        return dict(device=self.device, saved=self.value, restored=self.value, verified=True)
