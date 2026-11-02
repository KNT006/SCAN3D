"""Use the previously qualified maintenance path, with this release's own records.

Temporary driver unload and PCIe unbind explicitly reconfirmed by the user.
This helper never commands motion or writes Flash.
"""
from pathlib import Path
HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'fpga-laser-20261001/laser-board'
source = (OLD / 'board_validation.py').read_text()
source = source.replace('B=Path(__file__).resolve().parent', f'B=Path({str(HERE)!r})')
source = source.replace(
    "run('systemctl start afc03-camera afc03-scanner')",
    "run('PYTHONPATH=/opt/afc03-scanner/vendor /usr/bin/python3 /root/deploy/capture-pipeline-20261004/host/boot_ready.py')\n        run('systemctl start afc03-camera afc03-scanner')"
)
exec(compile(source, str(HERE / 'maintenance-generated.py'), 'exec'))
