"""Build isolated source candidate; fresh stage markers and immutable inputs."""
from pathlib import Path
import json,hashlib,subprocess,time,re,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent;RUNS=HERE/'board/fpga/imx415_pcie_4k_Runs'
TD='D:/Anlogic/TD_6.2.1_Release_6.2.175.876/bin/td_commands_prompt.exe'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for name in ['integration','core','atomic','probe-equivalence']:
 v=json.loads((HERE/(name+'-validation.json')).read_text());assert v['passed']
 assert all(sha(Path(p))==h for p,h in v['sha256'].items()),name+' inputs changed'
checks={str(HERE/'rtl/spatial_mask.hex'):sha(HERE/'rtl/spatial_mask.hex')}
for stage in ['syn_1','phy_1']:
 folder=RUNS/stage
 tree=ET.fromstring((folder/'imx415_pcie_4k.prj').read_text(encoding='latin1').replace('&','&amp;'))
 for e in tree.iter('File'):
  p=Path(e.attrib['Path']);p=(folder/p).resolve() if not p.is_absolute() else p
  checks[str(p)]=sha(p)
 for p in folder.iterdir():
  if p.suffix in ['.cfg','.adc','.sdc','.tcl','.prj','.txt'] and p.name not in ('place_clock_utilization.txt','route_clock_utilization.txt'):checks[str(p)]=sha(p)
(HERE/'build-inputs.json').write_text(json.dumps(checks,indent=2))
results=[]
for stage,marker in [('syn_1','.opt_gate.end.f'),('phy_1','.opt_route.end.f')]:
 assert all(sha(Path(p))==h for p,h in checks.items()),'Inputs changed'
 folder=RUNS/stage;started=time.time();logpath=folder/'candidate-build.log'
 (HERE/'build-status.json').write_text(json.dumps(dict(stage=stage,running=True,started=started)))
 with logpath.open('w') as log:r=subprocess.run([TD,'direct.tcl'],cwd=folder,stdout=log,stderr=subprocess.STDOUT)
 text=logpath.read_text(errors='replace');errors=re.findall(r'^.*(?:\bERROR:|allocation failed|coredump|USR-8159).*$',text,re.M|re.I)
 passed=r.returncode==0 and (folder/marker).exists() and (folder/marker).stat().st_mtime>=started and not errors
 result=dict(stage=stage,passed=passed,seconds=time.time()-started,exit_code=r.returncode,errors=errors)
 results.append(result);(HERE/'build-result.json').write_text(json.dumps(results,indent=2));print(json.dumps(result),flush=True)
 (HERE/'build-status.json').write_text(json.dumps(dict(stage=stage,running=False,passed=passed)))
 if not passed:raise SystemExit(1)
