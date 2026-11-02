from pathlib import Path
import json,subprocess,time
H=Path(__file__).resolve().parent
while True:
 s=json.loads((H/'build-status.json').read_text())
 if not s['running']:
  if s.get('passed') and s['stage']=='phy_1':break
  if not s.get('passed'):raise RuntimeError(s)
 time.sleep(15)
def run(*args):
 r=subprocess.run(['D:/Anaconda3/python.exe',str(H/args[0]),*args[1:]],cwd=H)
 return r.returncode
run('audit.py')
assert run('inspect_reset.py')==0
assert run('validate_reset_mapping.py','--generate')==0
raise SystemExit(run('audit.py','--mapped'))
