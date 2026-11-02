"""Optimize second-route real timing under the normal audited constraints."""
from pathlib import Path
import json, hashlib, subprocess, time, shutil

HOME = Path('D:/PCle/_b28/fpga-gain-handshake-20261013')
RUN = HOME / 'board/fpga/imx415_pcie_4k_Runs/phy_1'
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

audit = (HOME / 'audit.tcl').read_text()
assert 'import_db imx415_pcie_4k_pr.db' in audit
assert 'mapped-reset.sdc' in audit
assert 'new-B-reset-placement.sdc' not in audit
archive = HOME / 'second-route-before-eco'
archive.mkdir(exist_ok=False)
for p in [HOME/'strict-audit.log', HOME/'audit.tcl', HOME/'timing-qualification.json',
          HOME/'eco-result.json', HOME/'post-route-new-B.log',
          *HOME.glob('*-local.timing'), *RUN.glob('strict-laser-*.timing')]:
    if p.exists():
        shutil.copy2(p, archive/p.name)
s = audit.split('update_timing -mode final')[0] + '''update_timing -mode final
report_timing_summary -file laser-before-eco.timing
phys_opt -post_route -effort ultra
fix_hold
update_timing -mode final
report_timing_summary -file laser-after-eco.timing
check_timing -verbose -file laser-after-eco-check.timing
export_db imx415_pcie_4k_eco.db
} reason]} {puts stderr $reason; exit 1}
exit 0
'''
script = HOME/'post-route-new-B-round2.tcl'
script.write_text(s)
started = time.time()
with (HOME/'post-route-new-B-round2.log').open('w') as f:
    r = subprocess.run(['D:/Anlogic/TD_6.2.1_Release_6.2.175.876/bin/td_commands_prompt.exe',
                        script.as_posix()], cwd=RUN, stdout=f, stderr=subprocess.STDOUT)
log = (HOME/'post-route-new-B-round2.log').read_text(errors='replace')
db = RUN/'imx415_pcie_4k_eco.db'
passed = (r.returncode == 0 and db.exists() and db.stat().st_mtime >= started
          and not any(x in log for x in ['ERROR:', 'USR-8159', 'allocation failed', 'coredump']))
record = dict(completed=passed, exit_code=r.returncode, started=started,
              seconds=time.time()-started, script_sha256=sha(script),
              constraint_sha256=sha(HOME/'mapped-reset.sdc'),
              input_db_sha256=sha(RUN/'imx415_pcie_4k_pr.db'),
              output_db_sha256=sha(db) if passed else None,
              optimization_constraints='normal audited timing; no extra budget',
              timing_qualified=False)
(HOME/'eco-result.json').write_text(json.dumps(record, indent=2))
print(json.dumps(record, indent=2))
raise SystemExit(0 if passed else 1)
