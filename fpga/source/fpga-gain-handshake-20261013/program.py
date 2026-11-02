"""Program only the hash-verified, offline-qualified gain-handshake candidate."""
from pathlib import Path
import json,hashlib,subprocess,time,sys
H=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
q=json.loads((H/'qualified.json').read_text());bit=Path(q['bit'])
assert sha(bit)==q['sha256']
assert json.loads((H/'timing-qualification.json').read_text())['passed']
for name in ('gain-validation.json','gain-i2c-validation.json'):
 v=json.loads((H/name).read_text());assert v['passed']
 assert all(sha(Path(p))==h for p,h in v['sha256'].items())
mode=sys.argv[1];assert mode in ('sram','flash')
if mode=='flash':
 h=json.loads((H/'hardware-validation.json').read_text())
 assert h['passed'] and h['sha256']==q['sha256'] and q['hardware_validated']
op='JTAG' if mode=='sram' else 'program_spi -v'
tcl=H/('program-'+mode+'.tcl')
tcl.write_text('if {[catch {\nconnect_cable -host_name 127.0.0.1:5555\ndownload -bit {'+bit.as_posix()+'} -mode '+op+' -spd 6 -cable 0\n} reason]} {puts stderr $reason; exit 1}\nexit 0\n')
started=time.time()
with (H/('program-'+mode+'.log')).open('w') as f:
 r=subprocess.run(['D:/Anlogic/TD_6.2.1_Release_6.2.175.876/bin/bw_commands_prompt.exe',tcl.as_posix()],cwd=H,stdout=f,stderr=subprocess.STDOUT)
log=(H/('program-'+mode+'.log')).read_text(errors='replace')
passed=r.returncode==0 and 'Chip validation success: PH1A90' in log and 'finish command "download ' in log and not any(x in log.lower() for x in ('error:','failed','mismatch'))
if mode=='flash':passed=passed and 'SPI flash Page program and verify' in log
result=dict(passed=passed,exit_code=r.returncode,seconds=time.time()-started,sha256=q['sha256'],mode=mode,flash_written=passed and mode=='flash',cold_boot_tested=False)
(H/('program-'+mode+'-result.json')).write_text(json.dumps(result,indent=2));print(json.dumps(result));assert passed
