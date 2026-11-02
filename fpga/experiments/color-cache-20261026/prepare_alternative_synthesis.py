"""Prepare an isolated official TD synthesis strategy for congestion experiments."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path


def prepare(work, td, strategy_name, run_name):
    work, td = Path(work).resolve(), Path(td).resolve()
    assert (work / 'color-cache-candidate.json').is_file()
    runs = work / 'fpga-gain-handshake-20261013/board/fpga/imx415_pcie_4k_Runs'
    original, target = runs / 'syn_1', runs / run_name
    assert run_name.startswith('syn_') and not target.exists()
    strategy_file = td / 'doc/strategies/official_strategy_ph1.json'
    strategy = json.loads(strategy_file.read_text())[strategy_name]
    assert strategy['is_syn'] == 'syn'
    flow = (original / 'BoardFlow.tcl').read_text()
    for stage in ('rtl', 'gate'):
        commands = [f"  set_param {stage} {p['param']} {p['val']}"
                    for p in strategy['params'] if p['step'] == stage]
        if commands:
            marker = f'### Editable zone for opt_{stage} ###'
            assert flow.count(marker) == 1
            flow = flow.replace(marker, marker + '\n' + '\n'.join(commands))
    target.mkdir()
    for filename in ('settings.cfg', 'imx415_pcie_4k.prj', 'ref100.sdc',
                     'ddr-instances.adc', 'ddr-pins.adc', 'ddr-late.adc',
                     'afc03_ddr_cfg_rom.txt', 'afc03_ddr_mcu_rom.txt', 'direct.tcl'):
        shutil.copy2(original / filename, target / filename)
    cfg = target / 'settings.cfg'
    text = cfg.read_text().replace(
        (work / 'fpga-laser-20261001/rgb-roi/strict-afc03_camera_cdc.sdc').as_posix(),
        (work / 'fpga-gain-handshake-20261013/camera-cdc-alias.sdc').as_posix())
    text += '\nlappend SDCList {' + (work / 'fpga-gain-handshake-20261013/color-cdc.sdc').as_posix() + '}\n'
    cfg.write_text(text)
    (target / 'BoardFlow.tcl').write_text(flow)
    (target / 'strategy-provenance.json').write_text(json.dumps({
        'name': strategy_name, 'source': str(strategy_file),
        'source_sha256': hashlib.sha256(strategy_file.read_bytes()).hexdigest(),
        'strategy': strategy, 'rtl_and_ip_unchanged': True,
        'timing_constraints_unchanged': True, 'started': False,
    }, indent=2))
    print(target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--td', type=Path, required=True)
    parser.add_argument('--strategy', default='AreaOptimizeMedium')
    parser.add_argument('--name', default='syn_area_medium')
    args = parser.parse_args()
    prepare(args.work, args.td, args.strategy, args.name)
