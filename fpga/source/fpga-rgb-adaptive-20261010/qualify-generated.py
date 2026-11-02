from pathlib import Path
L=Path('F:\\AAA_FPGA\\afc03-esp32-motor\\fpga-rgb-adaptive-20261010');P=Path('F:\\AAA_FPGA\\afc03-esp32-motor\\fpga-laser-20261001')
from pathlib import Path
import json,re,hashlib,sys
from check_cdc import validate
from check_cdc import paths
R=Path('F:\\AAA_FPGA\\afc03-esp32-motor\\fpga-rgb-adaptive-20261010\\board\\fpga\\imx415_pcie_4k_Runs\\phy_1')
build=json.loads((L/'build-result.json').read_text());inputs=json.loads((L/'build-inputs.json').read_text())
summary=(R/'strict-laser-pr.timing').read_text(errors='replace');check=(R/'strict-laser-check.timing').read_text(errors='replace');log=(L/'strict-audit.log').read_text(errors='replace')
m=re.search(r'SWNS:\s*(-?[\d.]+)ns.*?HWNS:\s*(-?[\d.]+)ns',summary,re.S);assert m,'No whole-board WNS'
setup,hold=map(float,m.groups());counts={n:int(v) for n,v in re.findall(r'checking ([^\r\n(]+)\((\d+)\)',check)}
changed=[p for p,h in inputs.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h]
errors=re.findall(r'^.*(?:\bERROR:|USR-8159|allocation failed|coredump).*$',log,re.M|re.I)
cdc=validate(L/'routed-cdc-evidence',L/'strict-audit.log');(L/'routed-cdc-evidence/routed-coverage.json').write_text(json.dumps(cdc,indent=2))
fresh=(R/'strict-laser-pr.timing').stat().st_mtime>=(R/'.opt_route.end.f').stat().st_mtime and all(p.stat().st_mtime>=(R/'.opt_route.end.f').stat().st_mtime for p in (L/'routed-cdc-evidence').glob('*.timing'))
missing=[n for n in ['/pcie_user_clk','u_ddr_test/u_ddr/dfi_clk','u_ui_pll/pll_inst.clkc[2]','U_io_clk_div_0.clkout','U_io_clk_div_1.clkdivout'] if n not in summary]
passed=fresh and not changed and not errors and not missing and cdc['passed'] and setup>=0 and hold>=0 and all(counts.get(k)==0 for k in ['invalid constraint','combinational loops','soft fifo timing exception constraints']) and {v['stage'] for v in build}=={'syn_1','phy_1'} and all(v['passed'] for v in build)
reset_checks=[]
if '--eco' in sys.argv:
 eco=json.loads((L/'eco-result.json').read_text())
 passed=passed and eco['completed'] and hashlib.sha256((L/'mapped-reset.sdc').read_bytes()).hexdigest()==eco['constraint_sha256'] and (R/'strict-laser-pr.timing').stat().st_mtime>=eco['started']+eco['seconds']
 for name in ['u_dbg_snapshot','u_cam_config_snapshot']:
  t=(L/(name+'-reset-local.timing')).read_text(errors='replace');ps=paths(t)
  expect={(name+'/u_dst_reset/pipe[0]',name+'/u_dst_reset/pipe[1]'),(name+'/u_dst_reset/pipe[1]',name+'/drst_n')}
  ok=len(ps)==4 and { (p['source_net'],p['destination_net']) for p in ps}==expect and all(p['slack_ns']>=0 and p['launch_clock']==p['capture_clock'] for p in ps) and {p['check'] for p in ps}=={'setup','hold'}
  reset_checks.append(dict(instance=name,local_paths_timed=ok,paths=ps));passed=passed and ok
from validate_reset_mapping import validate_reset_mapping
reset_mapping=validate_reset_mapping()
reset_checks=reset_mapping['local_checks']
passed=passed and reset_mapping['passed']
result=dict(passed=passed,setup_wns_ns=setup,hold_wns_ns=hold,changed_inputs=changed,errors=errors,missing_clocks=missing,fresh=fresh,check_timing=counts,cdc_passed=cdc['passed'],cdc_errors=cdc['errors'],hardware_validated=False,flash_written=False)
result['reset_local_checks']=reset_checks
(L/'timing-qualification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2));sys.exit(0 if passed else 1)
