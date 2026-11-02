"""Strict routed audit, retaining original clock/CDC coverage requirements."""
from pathlib import Path
import sys,subprocess,json,hashlib,time
HERE=Path(__file__).resolve().parent;OLD=HERE.parent/'fpga-laser-20261001/laser-board'
R=HERE/'board/fpga/imx415_pcie_4k_Runs/phy_1'
TD='D:/Anlogic/TD_6.2.1_Release_6.2.175.876/bin/td_commands_prompt.exe'
eco='--eco' in sys.argv
mapped=eco or '--mapped' in sys.argv
build=json.loads((HERE/'build-result.json').read_text());assert len(build)==2 and all(v['passed'] for v in build)
(HERE/'routed-cdc-evidence').mkdir(exist_ok=True)
s=(HERE/'audit-routed.tcl').read_text().replace((OLD/'routed-cdc-evidence').as_posix(),(HERE/'routed-cdc-evidence').as_posix())
extra='''set debug_cells [get_cells -quiet -hier {debug_hub_top/* auto_created_cwc*/*}]
if {[llength $debug_cells] != 0} {error "Unexpected production ChipWatcher cells"}
puts "PRODUCTION_CHIPWATCHER_CELLS 0"
''' # Exact physical reset cells are inspected separately from current timing.
for name in ['u_dbg_snapshot','u_cam_config_snapshot']:
 extra+=f'report_timing_path -from [get_regs {{{name}/u_dst_reset/pipe[0] {name}/u_dst_reset/pipe[1]}}] -to [get_regs {{{name}/u_dst_reset/pipe[1] {name}/drst_n}}] -ep_num 8 -path_num 1 -file {{{(HERE/(name+"-reset-local.timing")).as_posix()}}}\n'
sample='u_cam_video_source/u_mipi_csi_rx/u_csi_rx_phy/gen_channel_wrapper[0]$u_csi_rx_hs_data_phy/gen_ph1a$'
extra+=f'report_timing_path -from [get_regs {{{sample}u_sample_reset/pipe[0] {sample}u_sample_reset/pipe[1]}}] -to [get_regs {{{sample}u_sample_reset/pipe[1] {sample}sample_reset_n}}] -ep_num 8 -path_num 1 -file {{{(HERE/"camera-sample-reset-local.timing").as_posix()}}}\n'
watchdog='u_cam_video_source/u_mipi_csi_rx/u_csi_rx_phy/u_csi_rx_clock_det/u_watchdog/'
extra+=f'report_timing_path -from [get_regs {{{watchdog}u_ext_reset/pipe[0] {watchdog}u_ext_reset/pipe[1]}}] -to [get_regs {{{watchdog}u_ext_reset/pipe[1] {watchdog}erst_n}}] -ep_num 8 -path_num 1 -file {{{(HERE/"camera-watchdog-reset-local.timing").as_posix()}}}\n'
s=s.replace('export_db strict-laser-pr.db',extra+'export_db strict-laser-pr.db')
if eco:
 s=s.replace('import_db imx415_pcie_4k_pr.db','import_db imx415_pcie_4k_eco.db')
if mapped:
 s=s.replace('update_timing -mode final','read_sdc {'+(HERE/'mapped-reset.sdc').as_posix()+'}\nupdate_timing -mode final',1)
(HERE/'audit.tcl').write_text(s)
with (HERE/'strict-audit.log').open('w') as f:r=subprocess.run([TD,(HERE/'audit.tcl').as_posix()],cwd=R,stdout=f,stderr=subprocess.STDOUT)
assert r.returncode==0
sys.path.insert(0,str(HERE))
q=(OLD/'qualify.py').read_text().replace('from sources import L,P',f'from pathlib import Path\nL=Path({str(HERE)!r});P=Path({str(OLD.parent)!r})')
q=q.replace("R=P/'board-laser/fpga/imx415_pcie_4k_Runs/phy_1'",f'R=Path({str(R)!r})')
q=q.replace("L/'board-build-result.json'","L/'build-result.json'").replace("json.loads((L/'board-inputs.json').read_text())['sha256']","json.loads((L/'build-inputs.json').read_text())")
if mapped:
 q=q.replace('result=dict(passed=',"from validate_reset_mapping import validate_reset_mapping\nreset_mapping=validate_reset_mapping()\nreset_checks=reset_mapping['local_checks']\npassed=passed and reset_mapping['passed']\nresult=dict(passed=")
(HERE/'qualify-generated.py').write_text(q)
exec(compile(q,str(HERE/'qualify-generated.py'),'exec'))
