"""Preserve the baseline constraints while resolving a proven reset alias.

TD merged mipi_monitor_reset into u_cam_eye_snapshot/u_src_reset. Its two
physical cells were checked in reset-alias-probe.log: ASR=user_link_up and
registered outputs are only pipe[0], pipe[1], srst_n. The alias is already
included by the baseline snapshot reset exception; this avoids an empty legacy
selector, not a new exception to functional paths. Recheck on the final netlist.
"""
import argparse
from pathlib import Path


def prepare(work):
    work = Path(work).resolve()
    assert (work / 'color-cache-candidate.json').is_file()
    base = work / 'fpga-laser-20261001/rgb-roi/strict-afc03_camera_cdc.sdc'
    source = base.read_text()
    old = 'u_mipi_monitor_reset/pipe_reg*.*sr */u_al_pcie_ip_msi_pipeline/u_msi_negedge_reset/pipe_reg*.*sr'
    new = 'u_mipi_monitor_reset/pipe_reg*.*sr u_cam_eye_snapshot/u_src_reset/pipe_reg*.*sr */u_al_pcie_ip_msi_pipeline/u_msi_negedge_reset/pipe_reg*.*sr'
    assert source.count(old) == 1
    target = work / 'fpga-gain-handshake-20261013/camera-cdc-alias.sdc'
    target.write_text(source.replace(old, new))
    print(target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    prepare(parser.parse_args().work)
