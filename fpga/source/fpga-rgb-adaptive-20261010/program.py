"""Load only the current bit with matching routed and integration evidence."""
from pathlib import Path
import json,hashlib,subprocess,time,sys
HERE=Path(__file__).resolve().parent
q=json.loads((HERE/'qualified.json').read_text());bit=Path(q['bit'])
assert hashlib.sha256(bit.read_bytes()).hexdigest()==q['sha256']
assert json.loads((HERE/'timing-qualification.json').read_text())['passed']
assert json.loads((HERE/'integration-validation.json').read_text())['passed']
mode=sys.argv[1] if len(sys.argv)>1 else 'sram';assert mode in ('sram','flash')
if mode=='flash':
 h=json.loads((HERE/'hardware-validation.json').read_text())
 assert h['passed'] and h['sha256']==q['sha256'] and q['hardware_validated']
 assert json.loads((HERE/'activated-host.json').read_text())['passed']
tcl=HERE/('program-'+mode+'.tcl')
operation='JTAG' if mode=='sram' else 'program_spi -v'
tcl.write_text('if {[catch {\nconnect_cable -host_name 127.0.0.1:5555\ndownload -bit {'+bit.as_posix()+'} -mode '+operation+' -spd 6 -cable 0\n} reason]} {puts stderr $reason; exit 1}\nexit 0\n')
start=time.time()
with (HERE/('program-'+mode+'.log')).open('w') as log:r=subprocess.run(['D:/Anlogic/TD_6.2.1_Release_6.2.175.876/bin/bw_commands_prompt.exe',tcl.as_posix()],cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
text=(HERE/('program-'+mode+'.log')).read_text(errors='replace')
passed=r.returncode==0 and 'Chip validation success: PH1A90' in text and 'finish command "download ' in text and not any(s in text.lower() for s in ['error:','failed','mismatch'])
if mode=='flash':passed=passed and 'SPI flash Page program and verify' in text
report=dict(exit_code=r.returncode,seconds=time.time()-start,sha256=q['sha256'],mode=mode,passed=passed,flash_written=passed and mode=='flash',log_review_required=False,cold_boot_tested=False)
(HERE/('program-result.json' if mode=='sram' else 'program-flash-result.json')).write_text(json.dumps(report,indent=2));print(json.dumps(report));assert passed
