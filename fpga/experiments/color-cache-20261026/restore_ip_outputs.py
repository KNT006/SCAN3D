"""Restore omitted IP outputs into a prepared candidate, only with identical IPC configs.

Never regenerate IP parameters or alter the repository's qualified source tree.
The donor is a full copy of the same board project, not another device's SGDMA example.
"""
import argparse
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--donor-board', type=Path, required=True)
    args = parser.parse_args()
    work, donor = args.work.resolve(), args.donor_board.resolve()
    assert (work / 'color-cache-candidate.json').is_file(), 'Not a prepared candidate'
    root = work / 'fpga-gain-handshake-20261013'
    board = root / 'sources/fpga-capture-pipeline-20261004/board/fpga'
    prj = root / 'board/fpga/imx415_pcie_4k_Runs/syn_1/imx415_pcie_4k.prj'
    # TD's XML contains literal P&R attributes; select the IP section without rewriting it.
    block = prj.read_text(encoding='latin1').split('<IP_FILE>')[1].split('</IP_FILE>')[0]
    pairs, configs = [], []
    for name in re.findall(r'<File Path="([^"]+)"', block):
        target = (prj.parent / name).resolve()
        source = donor / target.relative_to(board)
        tree, original = ET.parse(target), ET.parse(source)
        assert ET.tostring(tree.getroot()) == ET.tostring(original.getroot()), str(target)
        configs.append(dict(config=str(target.relative_to(work)), sha256=digest(target),
                            donor_config_sha256=digest(source), xml_equal=True))
        for generated in tree.findall('./GeneratedFiles/*'):
            # TD checks even disabled VHDL outputs for presence.
            pairs.append((source.parent / generated.text, target.parent / generated.text))
        if target.name == 'PH1_LOGIC_PCIE.ipc':
            # Referenced by the generated PCIe primitive and its configuration ROM.
            for suffix in ('txt', 'dat'):
                pairs.append((source.parent / ('al_pcie_ip.' + suffix),
                              target.parent / ('al_pcie_ip.' + suffix)))
    for name in ('afc03_ddr_mcu_rom.txt', 'afc03_ddr_cfg_rom.txt'):
        pairs.append((work / 'fpga-laser-20261001/vendor-ip/afc03_ddr' / name,
                      root / 'sources/fpga-laser-20261001/vendor-ip/afc03_ddr' / name))
    # Validate the full plan before any copy; never replace a differing existing output.
    for source, target in pairs:
        assert source.is_file(), str(source)
        assert target.is_relative_to(work), str(target)
        assert not target.exists() or digest(source) == digest(target), str(target)
    records = []
    for source, target in pairs:
        existed = target.exists()
        if not existed:
            shutil.copy2(source, target)
        records.append(dict(source=str(source), target=str(target.relative_to(work)),
                            sha256=digest(target), already_present=existed))
    (work / 'restored-ip-inputs.json').write_text(
        json.dumps(dict(configs=configs, outputs=records), indent=2), encoding='utf8')
    print('Verified/restored', len(records), 'outputs; all IPC configurations identical')


if __name__ == '__main__':
    main()
