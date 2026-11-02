"""Fresh timing/CDC qualification; never substitute historical pass reports."""
from pathlib import Path
import hashlib,json,re,sys
HOME=Path('D:/PCle/_b28/fpga-gain-handshake-20261013')
HERE=Path(__file__).resolve().parent
RUN=HOME/'board/fpga/imx415_pcie_4k_Runs/phy_1'
sys.path.insert(0,str(HOME))
from check_cdc import validate,paths
from validate_reset_mapping import validate_reset_mapping
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
build=json.loads((HOME/'build-result.json').read_text())
inputs=json.loads((HOME/'build-inputs.json').read_text())
summary=(RUN/'strict-laser-pr.timing').read_text(errors='replace')
check=(RUN/'strict-laser-check.timing').read_text(errors='replace')
log=(HOME/'strict-audit.log').read_text(errors='replace')
m=re.search(r'SWNS:\s*(-?[\d.]+)ns.*?HWNS:\s*(-?[\d.]+)ns',summary,re.S);assert m
setup,hold=map(float,m.groups())
counts={n:int(v) for n,v in re.findall(r'checking ([^\r\n(]+)\((\d+)\)',check)}
changed=[p for p,h in inputs.items() if sha(Path(p))!=h]
errors=re.findall(r'^.*(?:\bERROR:|USR-8159|allocation failed|coredump).*$',log,re.M|re.I)
cdc=validate(HOME/'routed-cdc-evidence',HOME/'strict-audit.log')
(HOME/'routed-cdc-evidence/routed-coverage.json').write_text(json.dumps(cdc,indent=2))
missing=[n for n in ['/pcie_user_clk','u_ddr_test/u_ddr/dfi_clk','u_ui_pll/pll_inst.clkc[2]','U_io_clk_div_0.clkout','U_io_clk_div_1.clkdivout'] if n not in summary]
fresh=all(p.stat().st_mtime>=(RUN/'.opt_route.end.f').stat().st_mtime for p in [RUN/'strict-laser-pr.timing',*list((HOME/'routed-cdc-evidence').glob('*.timing'))])
if 'import_db imx415_pcie_4k_eco.db' in (HOME/'audit.tcl').read_text():
    eco=json.loads((HOME/'eco-result.json').read_text())
    fresh=fresh and eco['completed'] and sha(RUN/'imx415_pcie_4k_eco.db')==eco['output_db_sha256'] and (RUN/'strict-laser-pr.timing').stat().st_mtime>=eco['started']+eco['seconds']
reset=validate_reset_mapping()
# Preserve raw stage failure/warnings. Only final independent audit can resolve
# the one known merged-register selector warning from intermediate placement.
route=build[1]
reviewed=all('USR-8159' in e and 'u_mipi_monitor_reset/pipe_reg' in e for e in route['errors'])
route_completed=route['exit_code']==0 and reviewed and not route['changed_inputs']
alias_record=json.loads((HOME/'monitor-alias-validation.json').read_text())
alias=alias_record['passed'] and alias_record['log_sha256']==sha(HOME/'strict-audit.log')
monitor=paths((HOME/'monitor-reset-local.timing').read_text())
expected={('u_cam_eye_snapshot/u_src_reset/pipe[0]','u_cam_eye_snapshot/u_src_reset/pipe[1]'),('u_cam_eye_snapshot/u_src_reset/pipe[1]','u_cam_eye_snapshot/srst_n')}
monitor_ok=len(monitor)==4 and {(p['source_net'],p['destination_net']) for p in monitor}==expected and all(p['slack_ns']>=0 and p['launch_clock']==p['capture_clock'] for p in monitor) and {p['check'] for p in monitor}=={'setup','hold'}
exception=(RUN/'strict-laser-exception.timing').read_text()
camera_crossings=[line for line in exception.splitlines() if re.match(r'^\s+13\s+13\s+0\s+0\s+set_max_delay',line) and 'hs_data_fifo/' in line and 'primary_addr_gray_reg*' in line and line.rstrip().endswith('6')]
clock_warnings=cdc['other_clock_warnings_requiring_separate_audit']
# TD emits these while deriving clocks, before its final constraint resolution.
# Require both camera buses fully constrained (13/13 each, no invalid/ignored
# endpoints), all named final clocks, and the independent 94-bit laser audit.
clocks_verified=(not missing and len(camera_crossings)==2 and all("No clocks matched 'get_clocks */pcie_user_clk'" in w for w in clock_warnings) and counts.get('invalid constraint')==0 and counts.get('clock definition')==0 and cdc['passed'])
passed=(build[0]['passed'] and route_completed and alias and monitor_ok and fresh and not changed and not errors and clocks_verified and cdc['passed'] and reset['passed'] and setup>=0 and hold>=0 and all(counts.get(k)==0 for k in ['invalid constraint','combinational loops','soft fifo timing exception constraints']) and 'PRODUCTION_CHIPWATCHER_CELLS 0' in log)
result=dict(passed=passed,setup_wns_ns=setup,hold_wns_ns=hold,changed_inputs=changed,errors=errors,missing_clocks=missing,fresh=fresh,check_timing=counts,cdc_passed=cdc['passed'],cdc_errors=cdc['errors'],reset_mapping_passed=reset['passed'],intermediate_route_warnings=route['errors'],reset_alias_proven=alias,route_completed=route_completed,hardware_validated=False,flash_written=False,rom_sha256=sha(HOME/'rtl/spatial_mask.hex'),audit_script_sha256=sha(HOME/'audit.tcl'),audit_camera_constraint_sha256=sha(HOME/'camera-cdc-mapped-alias.sdc'))
result.update(monitor_release_timed=monitor_ok,monitor_release_paths=monitor,other_clock_warnings=cdc['other_clock_warnings_requiring_separate_audit'])
result.update(final_pcie_clock_constraints_verified=clocks_verified,camera_crossing_constraint_coverage=camera_crossings)
for p in [HOME/'timing-qualification.json',HERE/'timing-qualification.json']:p.write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2));raise SystemExit(0 if passed else 1)
