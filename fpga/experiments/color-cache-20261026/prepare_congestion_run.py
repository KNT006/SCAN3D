"""Prepare an isolated run using TD's installed PH1 CongestionHigh strategy."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path


def prepare(work, td):
    work, td = Path(work).resolve(), Path(td).resolve()
    assert (work / 'color-cache-candidate.json').is_file()
    runs = work / 'fpga-gain-handshake-20261013/board/fpga/imx415_pcie_4k_Runs'
    original, target = runs / 'phy_1', runs / 'phy_congestion_high'
    strategy_file = td / 'doc/strategies/official_strategy_ph1.json'
    strategy = json.loads(strategy_file.read_text())['CongestionHigh']
    assert strategy['is_syn'] == 'phy'
    commands = {}
    for entry in strategy['params']:
        stage = entry['step']
        assert stage in ('place', 'route')
        commands.setdefault(stage, []).append(
            f"  set_param {stage} {entry['param']} {entry['val']}")
    flow = (original / 'BoardFlow.tcl').read_text()
    for stage in ('place', 'route'):
        needle = f'\n  {stage}\n'
        assert flow.count(needle) == 1
        flow = flow.replace(needle, '\n' + '\n'.join(commands[stage]) + needle)
    target.mkdir(exist_ok=False)
    for filename in ('settings.cfg', 'imx415_pcie_4k.prj', 'ref100.sdc',
                     'ddr-instances.adc', 'ddr-pins.adc', 'direct.tcl'):
        shutil.copy2(original / filename, target / filename)
    (target / 'BoardFlow.tcl').write_text(flow)
    (target / 'strategy-provenance.json').write_text(json.dumps({
        'name': 'CongestionHigh', 'source': str(strategy_file),
        'source_sha256': hashlib.sha256(strategy_file.read_bytes()).hexdigest(),
        'strategy': strategy, 'rtl_and_ip_unchanged': True,
        'timing_constraints_unchanged': True, 'started': False,
    }, indent=2))
    print(target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--td', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.work, args.td)
