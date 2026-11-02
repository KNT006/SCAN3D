from pathlib import Path
import subprocess,json,hashlib
H=Path(__file__).resolve().parent; B=H.parent/'capture-repair-20260928/tools/bin'
ss=[H/'rtl'/n for n in ['afc03_capture_admission.sv','afc03_rgb_roi_probe.sv','afc03_camera_roi_tap.sv']]+[H/'tb_atomic.sv']
r=subprocess.run([str(B/'iverilog.exe'),'-g2012','-s','tb','-o',str(H/'atomic.vvp'),*map(str,ss)],capture_output=True,text=True)
(H/'atomic-compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr
r=subprocess.run([str(B/'vvp.exe'),str(H/'atomic.vvp')],capture_output=True,text=True,timeout=20)
(H/'atomic-test.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
(H/'atomic-validation.json').write_text(json.dumps(dict(passed=True,output=r.stdout,sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in ss}),indent=2));print(r.stdout)
