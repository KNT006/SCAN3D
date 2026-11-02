"""Continue the isolated new-B build; record fresh inputs and route evidence."""
from pathlib import Path
import hashlib,json,re,subprocess,time,xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
HOME=Path('D:/PCle/_b28/fpga-gain-handshake-20261013')
RUNS=HOME/'board/fpga/imx415_pcie_4k_Runs'
TD='D:/Anlogic/TD_6.2.1_Release_6.2.175.876/bin/td_commands_prompt.exe'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def errors(s): return re.findall(r'^.*(?:\bERROR:|allocation failed|coredump|USR-8159).*$',s,re.M|re.I)
syn=RUNS/'syn_1'
assert (syn/'.opt_gate.end.f').exists() and not errors((syn/'new-b-build.log').read_text(errors='replace'))
assert (syn/'.opt_gate.end.f').stat().st_mtime >= (syn/'new-b-build.log').stat().st_ctime
inputs={}
for stage in ['syn_1','phy_1']:
    folder=RUNS/stage
    tree=ET.fromstring((folder/'imx415_pcie_4k.prj').read_text(encoding='latin1').replace('&','&amp;'))
    for entry in tree.iter('File'):
        p=Path(entry.attrib['Path']); p=(folder/p).resolve() if not p.is_absolute() else p
        inputs[str(p)]=sha(p)
    for p in folder.iterdir():
        if p.suffix in ('.cfg','.sdc','.adc','.tcl','.prj') or p.name.endswith('_rom.txt'): inputs[str(p)]=sha(p)
for p in (HOME/'rtl').iterdir():
    if p.is_file(): inputs[str(p)]=sha(p)
placement_budget=HOME/'new-B-reset-placement.sdc'
if placement_budget.exists(): inputs[str(placement_budget)]=sha(placement_budget)
assert sha(HOME/'rtl/spatial_mask.hex')==json.loads((HERE/'rom-validation.json').read_text())['rom_sha256']
(HOME/'build-inputs.json').write_text(json.dumps(inputs,indent=2))
results=[dict(stage='syn_1',passed=True,exit_code=0,errors=[],log_sha256=sha(syn/'new-b-build.log'))]
(HOME/'build-result.json').write_text(json.dumps(results,indent=2))
folder=RUNS/'phy_1'; started=time.time()
with (folder/'new-b-build.log').open('w') as log:
    r=subprocess.run([TD,'direct.tcl'],cwd=folder,stdout=log,stderr=subprocess.STDOUT)
errs=errors((folder/'new-b-build.log').read_text(errors='replace'))
marker=folder/'.opt_route.end.f'
changed=[p for p,h in inputs.items() if sha(Path(p))!=h]
passed=r.returncode==0 and marker.exists() and marker.stat().st_mtime>=started and not errs and not changed
results.append(dict(stage='phy_1',passed=passed,exit_code=r.returncode,errors=errs,changed_inputs=changed,started=started,seconds=time.time()-started,log_sha256=sha(folder/'new-b-build.log')))
for out in [HOME/'build-result.json',HERE/'build-result.json']: out.write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2),flush=True)
raise SystemExit(0 if passed else 1)
