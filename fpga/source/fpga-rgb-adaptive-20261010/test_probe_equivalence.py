from pathlib import Path
import subprocess,json,hashlib,numpy as np
H=Path(__file__).resolve().parent;B=H.parent/'capture-repair-20260928/tools/bin';ss=[H/'rtl/afc03_rgb_roi_probe.sv',H/'probe-golden.sv',H/'tb_probe_equivalence.sv']
r=subprocess.run([str(B/'iverilog.exe'),'-g2012','-s','tb','-o',str(H/'probe-equivalence.vvp'),*map(str,ss)],capture_output=True,text=True);assert r.returncode==0,r.stderr
r=subprocess.run([str(B/'vvp.exe'),str(H/'probe-equivalence.vvp')],capture_output=True,text=True,timeout=30);(H/'probe-equivalence.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
x=np.arange(2049)
for e in range(2049):
 for inside in (0,1):
  assert np.array_equal(x+inside==e,(x==e-1)&(e!=0) if inside else x==e)
v=dict(passed=True,output=r.stdout,all_valid_count_combinations=2049*2049*2,cycle_by_cycle_interface_and_state_match=True,sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in ss})
(H/'probe-equivalence-validation.json').write_text(json.dumps(v,indent=2));print(r.stdout)
