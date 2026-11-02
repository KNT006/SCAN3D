"""Inspect actual mapped reset cells; does not add exceptions automatically."""
from pathlib import Path
import subprocess,re,sys
H=Path(__file__).resolve().parent;R=H/'board/fpga/imx415_pcie_4k_Runs/phy_1'
tcl=H/'inspect-reset.tcl'
timing=R/'strict-laser-pr.timing'
if not timing.exists():timing=R/'imx415_pcie_4k_place.timing'
cells=sorted(set(re.findall(r'^End Point\s+: (\S+)\.asr ',timing.read_text(),re.M)))
# A correctly timed reset output need not be among the worst summary endpoints.
# Include cells identified by the independently reported local release paths.
for name in ['u_dbg_snapshot-reset-local.timing','u_cam_config_snapshot-reset-local.timing','camera-sample-reset-local.timing','camera-watchdog-reset-local.timing']:
    p=H/name
    if p.exists():
        cells+=re.findall(r'^(?:Begin|End) Point\s+: (\S+)\.\w+ ',p.read_text(),re.M)
cells=sorted(set(cells))
if '--eco' in sys.argv:
    cells=sorted(set(cells+[x.lstrip('{') for x in re.findall(r'(\S+)\.asr', (H/'mapped-reset.sdc').read_text())]))
assert cells,'No actual mapped reset endpoints found'
tcl.write_text('''import_device ph1_90.db -package PH1A90SEG324 -speed 2
open_project imx415_pcie_4k.prj -noanalyze
import_db imx415_pcie_4k_pr.db
report_cells [get_cells {RESET_CELLS}] -connection -pin_loc
get_regs {u_cam_video_source/u_mipi_csi_rx/u_csi_rx_phy/gen_channel_wrapper*u_csi_rx_hs_data_phy/gen_ph1a*u_sample_reset/pipe*} -verbose
exit 0
'''.replace('RESET_CELLS',' '.join(cells)).replace('import_db imx415_pcie_4k_pr.db',
    'import_db imx415_pcie_4k_eco.db' if '--eco' in sys.argv else 'import_db imx415_pcie_4k_pr.db'))
with (H/'inspect-reset.log').open('w') as f:
    r=subprocess.run(['D:/Anlogic/TD_6.2.1_Release_6.2.175.876/bin/td_commands_prompt.exe',tcl.as_posix()],cwd=R,stdout=f,stderr=subprocess.STDOUT)
assert r.returncode==0
print('Inspected',len(cells),'actual ASR endpoints; evidence:',H/'inspect-reset.log')
