"""Preserve first route, then official post-route high-effort closure. No JTAG."""
from pathlib import Path
L=Path('F:\\AAA_FPGA\\afc03-esp32-motor\\fpga-rgb-adaptive-20261010');P=L
import shutil,hashlib,json,subprocess,time
R=Path('F:\\AAA_FPGA\\afc03-esp32-motor\\fpga-rgb-adaptive-20261010\\board\\fpga\\imx415_pcie_4k_Runs\\phy_1');TD='D:/Anlogic/TD_6.2.1_Release_6.2.175.876/bin/td_commands_prompt.exe'
archive=L/'first-route';archive.mkdir(exist_ok=True)
for n in ['imx415_pcie_4k_pr.db','imx415_pcie_4k_pr.timing','imx415_pcie_4k_chk.timing','candidate-build.log']:
 shutil.copy2(R/n,archive/n)
script=(L/'audit-routed.tcl').read_text().split('update_timing -mode final')[0]
script+='read_sdc {'+(L/'mapped-reset.sdc').as_posix()+'}\n'
script+='''update_timing -mode final
report_timing_summary -file laser-before-eco.timing
phys_opt -post_route -effort high
fix_hold
update_timing -mode final
report_timing_summary -file laser-after-eco.timing
report_area -io_info -file laser-after-eco.area
check_timing -verbose -file laser-after-eco-check.timing
export_db imx415_pcie_4k_eco.db
exit 0
'''
(L/'post-route-eco.tcl').write_text(script)
start=time.time()
with (L/'post-route-eco.log').open('w') as f:r=subprocess.run([TD,(L/'post-route-eco.tcl').as_posix()],cwd=R,stdout=f,stderr=subprocess.STDOUT)
text=(L/'post-route-eco.log').read_text(errors='replace')
db=R/'imx415_pcie_4k_eco.db';passed=r.returncode==0 and db.exists() and db.stat().st_mtime>=start and not any(v in text for v in ['ERROR:','USR-8159','allocation failed','coredump'])
result=dict(completed=passed,exit_code=r.returncode,seconds=time.time()-start,started=start,script_sha256=hashlib.sha256((L/'post-route-eco.tcl').read_bytes()).hexdigest(),constraint_sha256=hashlib.sha256((L/'mapped-reset.sdc').read_bytes()).hexdigest(),input_db_sha256=hashlib.sha256((archive/'imx415_pcie_4k_pr.db').read_bytes()).hexdigest(),output_db_sha256=hashlib.sha256(db.read_bytes()).hexdigest() if passed else None,timing_qualified=False)
(L/'eco-result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result));raise SystemExit(0 if passed else 1)
