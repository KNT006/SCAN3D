"""Complete offline qualification after this candidate's ongoing build; never program hardware."""
from pathlib import Path
import subprocess,sys,json,time,re
H=Path(__file__).resolve().parent
started=time.time()
while True:
 status=json.loads((H/'build-status.json').read_text())
 if not status.get('running') and status.get('passed') is False:
  raise SystemExit('Build failed; no qualification attempted')
 if status.get('stage')=='phy_1' and not status.get('running'):
  assert status.get('passed');break
 if time.time()-started>3600:raise SystemExit('Build wait timeout; no hardware operation')
 time.sleep(5)
steps=[]
def run(script,*args,allow_failure=False):
 t=time.time()
 (H/'offline-status.json').write_text(json.dumps(dict(stage=script,args=args,running=True)))
 p=subprocess.run([sys.executable,str(H/script),*args],cwd=H,capture_output=True,text=True)
 tag=script.replace('.py','')+''.join(args)
 (H/(tag+'-runner.log')).write_text(p.stdout+p.stderr)
 result=dict(script=script,args=args,exit_code=p.returncode,seconds=time.time()-t)
 steps.append(result);(H/'offline-steps.json').write_text(json.dumps(steps,indent=2))
 print(json.dumps(result),flush=True)
 (H/'offline-status.json').write_text(json.dumps(dict(stage=script,args=args,running=False,passed=p.returncode==0)))
 if p.returncode and not allow_failure:raise SystemExit(p.returncode)
run('audit.py',allow_failure=True)
# An initial timing rejection due to physically packed asynchronous reset pins is
# expected on some placements. Only inspect newly generated, tool-error-free data.
log=(H/'strict-audit.log').read_text(errors='replace')
assert not re.search(r'ERROR:|USR-8159|allocation failed|coredump',log,re.I)
q=json.loads((H/'timing-qualification.json').read_text())
assert q['fresh'] and not q['changed_inputs'] and not q['missing_clocks'] and q['cdc_passed']
run('inspect_reset.py')
run('validate_reset_mapping.py','--generate')
run('audit.py','--mapped')
run('bitgen.py')
(H/'offline-status.json').write_text(json.dumps(dict(stage='complete',running=False,passed=True,hardware_validated=False,flash_written=False)))
