"""Fresh isolated synthesis and route, with no programming or production changes."""
from pathlib import Path
import json,hashlib,subprocess,time,re,xml.etree.ElementTree as ET
H=Path(__file__).parent;OLD=H.parent/'fpga-rgb-adaptive-20261010'
R=H/'board/fpga/imx415_pcie_4k_Runs'
TD='D:/Anlogic/TD_6.2.1_Release_6.2.175.876/bin/td_commands_prompt.exe'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
validation=json.loads((H/'gain-validation.json').read_text());assert validation['passed']
assert all(sha(Path(p))==v for p,v in validation['sha256'].items())
checks={};deltas=[]
for stage in ['syn_1','phy_1']:
 folder=R/stage
 for name in ['afc03_ddr_cfg_rom.txt','afc03_ddr_mcu_rom.txt']:
  p=folder/name
  assert p.is_file() and sha(p)==sha(OLD/'board/fpga/imx415_pcie_4k_Runs'/stage/name),f'DDR initialization missing or changed: {p}'
  checks[str(p)]=sha(p)
 tree=ET.fromstring((folder/'imx415_pcie_4k.prj').read_text(encoding='latin1').replace('&','&amp;'))
 for e in tree.iter('File'):
  p=Path(e.attrib['Path']);p=(folder/p).resolve() if not p.is_absolute() else p
  checks[str(p)]=sha(p)
  if p.is_relative_to(H):
   baseline=OLD/p.relative_to(H)
   if sha(baseline)!=sha(p):deltas.append(str(p))
 for p in folder.iterdir():
  if p.suffix in ['.cfg','.sdc','.adc','.tcl','.prj']:checks[str(p)]=sha(p)
for p in H.rglob('*'):
 if p.is_file() and p.suffix in ['.hex','.mem','.vh','.svh']:checks[str(p)]=sha(p)
assert set(Path(p).name for p in deltas)=={'ui_cfg_imx415.v'},deltas
(H/'build-inputs.json').write_text(json.dumps(checks,indent=2))
(H/'source-delta.json').write_text(json.dumps(dict(changed=sorted(set(deltas)),baseline=str(OLD),optical_extraction_rtl_unchanged=True),indent=2))
results=[]
for stage,marker in [('syn_1','.opt_gate.end.f'),('phy_1','.opt_route.end.f')]:
 assert all(sha(Path(p))==v for p,v in checks.items())
 folder=R/stage;started=time.time()
 (H/'build-status.json').write_text(json.dumps(dict(stage=stage,running=True,started=started)))
 with (folder/'candidate-build.log').open('w') as log:r=subprocess.run([TD,'direct.tcl'],cwd=folder,stdout=log,stderr=subprocess.STDOUT)
 txt=(folder/'candidate-build.log').read_text(errors='replace')
 errors=re.findall(r'^.*(?:\bERROR:|allocation failed|coredump|USR-8159).*$',txt,re.M|re.I)
 passed=r.returncode==0 and (folder/marker).exists() and (folder/marker).stat().st_mtime>=started and not errors
 result=dict(stage=stage,passed=passed,seconds=time.time()-started,exit_code=r.returncode,errors=errors)
 results.append(result);(H/'build-result.json').write_text(json.dumps(results,indent=2));print(json.dumps(result),flush=True)
 (H/'build-status.json').write_text(json.dumps(dict(stage=stage,running=False,passed=passed)))
 if not passed:raise SystemExit(1)
