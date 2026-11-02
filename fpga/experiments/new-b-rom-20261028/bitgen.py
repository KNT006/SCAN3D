"""Generate new-B candidate only after fresh timing/CDC/reset qualification."""
from pathlib import Path
import json,hashlib,subprocess,time,shutil
HERE=Path(__file__).resolve().parent
HOME=Path('D:/PCle/_b28/fpga-gain-handshake-20261013')
RUN=HOME/'board/fpga/imx415_pcie_4k_Runs/phy_1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
q=json.loads((HERE/'timing-qualification.json').read_text());assert q['passed']
inputs=json.loads((HOME/'build-inputs.json').read_text())
assert all(sha(Path(p))==h for p,h in inputs.items())
assert sha(HOME/'audit.tcl')==q['audit_script_sha256']
assert sha(HOME/'camera-cdc-mapped-alias.sdc')==q['audit_camera_constraint_sha256']
rom=json.loads((HERE/'rom-validation.json').read_text())
assert sha(HOME/'rtl/spatial_mask.hex')==rom['rom_sha256']==q['rom_sha256']
assert rom['baseline_rom_reproduced'] and rom['A_unchanged']
assert json.loads((HOME/'reset-mapping-validation.json').read_text())['passed']
assert json.loads((HOME/'routed-cdc-evidence/routed-coverage.json').read_text())['passed']
assert (RUN/'strict-laser-pr.db').stat().st_mtime>=(RUN/'.opt_route.end.f').stat().st_mtime
name='afc03-new-B-rom-20261028.bit'
script=HOME/'bitgen-new-B.tcl'
script.write_text('if {[catch {\nimport_device ph1_90.db -package PH1A90SEG324 -speed 2\nopen_project imx415_pcie_4k.prj -noanalyze\nimport_db strict-laser-pr.db\nbitgen -bit '+name+'\n} reason]} {puts stderr $reason; exit 1}\nexit 0\n')
started=time.time()
with (HOME/'bitgen-new-B.log').open('w') as f:
    p=subprocess.run(['D:/Anlogic/TD_6.2.1_Release_6.2.175.876/bin/td_commands_prompt.exe',script.as_posix()],cwd=RUN,stdout=f,stderr=subprocess.STDOUT)
bit=RUN/name;log=(HOME/'bitgen-new-B.log').read_text(errors='replace')
assert p.returncode==0 and bit.exists() and bit.stat().st_mtime>=started
assert not any(x in log for x in ['ERROR:','allocation failed','coredump'])
out=HERE/('candidate-'+time.strftime('%Y%m%d-%H%M%S'));out.mkdir()
shutil.copy2(bit,out/name)
for f in ['timing-qualification.json','rom-validation.json','source-delta.json']:
    shutil.copy2(HERE/f,out/f)
shutil.copytree(HERE/'bundle',out/'bundle')
record=dict(bit=str(out/name),sha256=sha(bit),bytes=bit.stat().st_size,rom_sha256=rom['rom_sha256'],calibration_hashes=rom['calibration_hashes'],timing_qualified=True,hardware_validated=False,flash_written=False,absolute_accuracy_validated=False,strict_db_sha256=sha(RUN/'strict-laser-pr.db'),timing_qualification_sha256=sha(HERE/'timing-qualification.json'),job_abi='0x00060000',c2h_channels=2)
(HERE/'candidate.json').write_text(json.dumps(record,indent=2));print(json.dumps(record,indent=2))
