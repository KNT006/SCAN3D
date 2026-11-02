"""Prepare isolated routed/reset audits; never treat placed reports as acceptance."""
import argparse
from pathlib import Path


def prepare(work, run):
    home = Path(work).resolve() / 'fpga-gain-handshake-20261013'
    source = Path(__file__).resolve().parents[2] / 'source/fpga-gain-handshake-20261013'
    assert run in ('phy_area_high', 'phy_1', 'phy_congestion_high', 'phy_route_complete')
    audit = (home / 'color-audit.tcl').read_text()
    # Include all 21 previously ignored legacy reply paths, not a 10-path sample.
    audit = audit.replace('report_timing_exception -ep_num 10',
                          'report_timing_exception -ep_num 128')
    audit = audit.replace('report_timing_ignored -ep_num 4',
                          'report_timing_ignored -ep_num 128')
    audit = audit.replace(
        (home.parent / 'fpga-laser-20261001/rgb-roi/strict-afc03_camera_cdc.sdc').as_posix(),
        (home / 'camera-cdc-alias.sdc').as_posix())
    eye_report = (home / 'camera-eye-reset-local.timing').as_posix()
    eye = ('report_timing_path -from [get_regs {u_cam_eye_snapshot/u_src_reset/pipe[0] '
           'u_cam_eye_snapshot/u_src_reset/pipe[1]}] -to [get_regs '
           '{u_cam_eye_snapshot/u_src_reset/pipe[1] u_cam_eye_snapshot/srst_n}] '
           '-ep_num 8 -path_num 1 -file {' + eye_report + '}\n')
    audit = audit.replace('export_db strict-laser-pr.db', eye + 'export_db strict-laser-pr.db')
    (home / 'final-color-audit.tcl').write_text(audit)
    inspect = (source / 'inspect_reset.py').read_text()
    inspect = inspect.replace("Runs/phy_1'", "Runs/" + run + "'")
    inspect = inspect.replace("'camera-watchdog-reset-local.timing']", 
                              "'camera-watchdog-reset-local.timing','camera-eye-reset-local.timing']")
    (home / 'inspect_color_reset.py').write_text(inspect)
    validator = (source / 'validate_reset_mapping.py').read_text()
    validator = validator.replace('from check_cdc import paths', 'from check_color_cdc import paths')
    (home / 'validate_color_reset_mapping.py').write_text(validator)
    print('Prepared audit for', home / 'board/fpga/imx415_pcie_4k_Runs' / run)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', required=True)
    parser.add_argument('--run', default='phy_area_high')
    args = parser.parse_args()
    prepare(args.work, args.run)
