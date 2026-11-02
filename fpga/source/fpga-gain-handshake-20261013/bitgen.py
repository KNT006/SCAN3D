from pathlib import Path
import json,hashlib,subprocess,shutil,time
H=Path(__file__).resolve().parent
BASELINE=H.parent/'fpga-rgb-adaptive-20261010'
R=H/'board/fpga/imx415_pcie_4k_Runs/phy_1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
q=json.loads((H/'timing-qualification.json').read_text());assert q['passed']
inputs=json.loads((H/'build-inputs.json').read_text());assert all(sha(Path(p))==h for p,h in inputs.items())
audit_text=(H/'audit.tcl').read_text()
assert (R/'strict-laser-pr.db').stat().st_mtime >= (R/'.opt_route.end.f').stat().st_mtime
if 'import_db imx415_pcie_4k_eco.db' in audit_text:
 eco=json.loads((H/'eco-result.json').read_text());assert eco['completed']
 assert (R/'imx415_pcie_4k_eco.db').stat().st_mtime >= (R/'.opt_route.end.f').stat().st_mtime
 assert sha(R/'imx415_pcie_4k_eco.db')==eco['output_db_sha256']
else:
 assert 'import_db imx415_pcie_4k_pr.db' in audit_text
 assert (R/'imx415_pcie_4k_pr.db').stat().st_mtime >= (R/'.opt_route.begin.f').stat().st_mtime
evidence=['timing-qualification.json','build-inputs.json','build-result.json','audit.tcl','laser-cdc.sdc','routed-cdc-evidence/routed-coverage.json','source-delta.json','change-manifest.json']
if 'import_db imx415_pcie_4k_eco.db' in audit_text:
 scripts=[p for p in H.glob('post-route-eco*.tcl') if sha(p)==eco['script_sha256']]
 assert len(scripts)==1,'Optimization script changed'
 evidence+=['eco-result.json',scripts[0].name]
 if 'optimize-reset-margin.sdc' in scripts[0].read_text():evidence.append('optimize-reset-margin.sdc')
for name in ['gain','gain-i2c']:
 p=H/(name+'-validation.json');v=json.loads(p.read_text());assert v['passed'],name
 if 'sha256' in v and isinstance(v['sha256'],dict):assert all(sha(Path(p))==h for p,h in v['sha256'].items()),name
 evidence.append(p.name)
# This release changes only the gain-config FSM. Record the actual baseline
# and prove unchanged compiled logic, without presenting old tests as new runs.
delta=json.loads((H/'source-delta.json').read_text())
assert len(delta['changed'])==1
assert Path(delta['changed'][0]).name=='ui_cfg_imx415.v'
for name,digest in inputs.items():
 p=Path(name)
 if p.suffix in ['.v','.sv','.hex','.mem','.vh','.svh'] and p.is_relative_to(H):
  old=BASELINE/p.relative_to(H)
  assert old.is_file()
  assert sha(p)==sha(old) or str(p) in delta['changed'],str(p)
baseline=json.loads((BASELINE/'qualified.json').read_text())
assert sha(Path(baseline['bit']))==baseline['sha256']
baseline_record=dict(kind='unchanged subsystem evidence from prior release; not rerun hardware validation',
 qualified_bit=baseline,changed_sources=delta['changed'],
 host_software_changed=False,scanning_algorithm_changed=False)
(H/'baseline-reference.json').write_text(json.dumps(baseline_record,indent=2))
evidence+=['baseline-reference.json','gain-case-0.log','gain-case-1.log','gain-case-2.log','gain-case-3.log','gain-case-4.log','gain-case-5.log','gain-case-6.log','gain-i2c.log','tb_gain.sv','tb_gain_i2c.sv']
assert 'PRODUCTION_CHIPWATCHER_CELLS 0' in (H/'strict-audit.log').read_text()
v=json.loads((H/'reset-mapping-validation.json').read_text());assert v['passed']
assert sha(H/'mapped-reset.sdc')==v['constraint_sha256'] and sha(H/'inspect-reset.log')==v['evidence_sha256']
evidence+=['mapped-reset.sdc','reset-mapping-validation.json','inspect-reset.log']
name='afc03-gain-handshake-v1.bit';tcl=H/'bitgen.tcl'
tcl.write_text('import_device ph1_90.db -package PH1A90SEG324 -speed 2\nopen_project imx415_pcie_4k.prj -noanalyze\nimport_db strict-laser-pr.db\nbitgen -bit '+name+'\nexit 0\n')
started=time.time()
with (H/'bitgen.log').open('w') as f:r=subprocess.run(['D:/Anlogic/TD_6.2.1_Release_6.2.175.876/bin/td_commands_prompt.exe',tcl.as_posix()],cwd=R,stdout=f,stderr=subprocess.STDOUT)
bit=R/name;assert r.returncode==0 and bit.exists() and bit.stat().st_mtime>=started
log=(H/'bitgen.log').read_text(errors='replace');assert not any(s in log for s in ('ERROR:','allocation failed','coredump'))
archive=H/('qualified-'+time.strftime('%Y%m%d-%H%M%S'));archive.mkdir()
for p in [bit,*[H/n for n in evidence]]:shutil.copy2(p,archive/p.name)
record=dict(bit=str(archive/name),sha256=sha(bit),bytes=bit.stat().st_size,hardware_validated=False,flash_written=False,strict_db_sha256=sha(R/'strict-laser-pr.db'),job_abi='0x00060000',c2h_channels=2,spatial_rom_sha256=sha(H/'rtl/spatial_mask.hex'))
(H/'qualified.json').write_text(json.dumps(record,indent=2));print(json.dumps(record))
