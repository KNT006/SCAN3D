"""Prepare, but do not start, the official PH1 AreaOptimizeHigh synthesis."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
from prepare_constraints import prepare as prepare_constraints


def prepare(work, td):
    work, td = Path(work).resolve(), Path(td).resolve()
    assert (work / 'color-cache-candidate.json').is_file()
    prepare_constraints(work)
    runs = work / 'fpga-gain-handshake-20261013/board/fpga/imx415_pcie_4k_Runs'
    original, target = runs / 'syn_1', runs / 'syn_area_high'
    strategy_file = td / 'doc/strategies/official_strategy_ph1.json'
    strategy = json.loads(strategy_file.read_text())['AreaOptimizeHigh']
    assert strategy['is_syn'] == 'syn'
    flow = (original / 'BoardFlow.tcl').read_text()
    for stage in ('rtl', 'gate'):
        marker = f'### Editable zone for opt_{stage} ###'
        assert flow.count(marker) == 1
        commands = '\n'.join(f"  set_param {stage} {p['param']} {p['val']}"
                             for p in strategy['params'] if p['step'] == stage)
        flow = flow.replace(marker, marker + '\n' + commands)
    target.mkdir(exist_ok=False)
    for filename in ('settings.cfg', 'imx415_pcie_4k.prj', 'ref100.sdc',
                     'ddr-instances.adc', 'ddr-pins.adc', 'ddr-late.adc',
                     'afc03_ddr_cfg_rom.txt', 'afc03_ddr_mcu_rom.txt', 'direct.tcl'):
        shutil.copy2(original / filename, target / filename)
    cfg = target / 'settings.cfg'
    cfg.write_text(cfg.read_text().replace(
        (work / 'fpga-laser-20261001/rgb-roi/strict-afc03_camera_cdc.sdc').as_posix(),
        (work / 'fpga-gain-handshake-20261013/camera-cdc-alias.sdc').as_posix()))
    # The added bank requires the same constraints in synthesis as in implementation.
    with (target / 'settings.cfg').open('a') as cfg:
        cfg.write('\nlappend SDCList {' +
                  (work / 'fpga-gain-handshake-20261013/color-cdc.sdc').as_posix() + '}\n')
    (target / 'BoardFlow.tcl').write_text(flow)
    (target / 'strategy-provenance.json').write_text(json.dumps({
        'name': 'AreaOptimizeHigh', 'source': str(strategy_file),
        'source_sha256': hashlib.sha256(strategy_file.read_bytes()).hexdigest(),
        'strategy': strategy, 'rtl_and_ip_unchanged': True, 'started': False,
    }, indent=2))
    print(target)


def prepare_physical(work):
    work = Path(work).resolve()
    runs = work / 'fpga-gain-handshake-20261013/board/fpga/imx415_pcie_4k_Runs'
    assert (runs / 'syn_area_high/strategy-provenance.json').is_file()
    source, target = runs / 'phy_1', runs / 'phy_area_high'
    target.mkdir(exist_ok=False)
    for filename in ('settings.cfg', 'imx415_pcie_4k.prj', 'ref100.sdc',
                     'ddr-instances.adc', 'ddr-pins.adc', 'direct.tcl', 'BoardFlow.tcl'):
        shutil.copy2(source / filename, target / filename)
    cfg = target / 'settings.cfg'
    text = cfg.read_text()
    assert text.count('set parent ../syn_1') == 1
    text = text.replace('set parent ../syn_1', 'set parent ../syn_area_high')
    text = text.replace(
        (work / 'fpga-laser-20261001/rgb-roi/strict-afc03_camera_cdc.sdc').as_posix(),
        (work / 'fpga-gain-handshake-20261013/camera-cdc-alias.sdc').as_posix())
    cfg.write_text(text)
    print(target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--td', type=Path, required=True)
    parser.add_argument('--physical-only', action='store_true')
    args = parser.parse_args()
    if args.physical_only:
        prepare_physical(args.work)
    else:
        prepare(args.work, args.td)
