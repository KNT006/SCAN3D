"""Load the qualified candidate to SRAM; Flash programming is separate."""
from pathlib import Path
import json, hashlib, subprocess, time
HERE=Path(__file__).resolve().parent
record=json.loads((HERE/'candidate.json').read_text())
bit=Path(record['bit'])
assert record['timing_qualified']
assert hashlib.sha256(bit.read_bytes()).hexdigest()==record['sha256']
script=HERE/'program-sram.tcl'
script.write_text('if {[catch {\nconnect_cable -host_name 127.0.0.1:5555\ndownload -bit {'+bit.as_posix()+'} -mode JTAG -spd 6 -cable 0\n} reason]} {puts stderr $reason; exit 1}\nexit 0\n')
started=time.time()
logfile=HERE/'program-sram.log'
with logfile.open('w') as f:
    r=subprocess.run(['D:/Anlogic/TD_6.2.1_Release_6.2.175.876/bin/bw_commands_prompt.exe',script.as_posix()],stdout=f,stderr=subprocess.STDOUT)
text=logfile.read_text(errors='replace')
result=dict(exit_code=r.returncode,started=started,seconds=time.time()-started,bit_sha256=record['sha256'],log_sha256=hashlib.sha256(logfile.read_bytes()).hexdigest(),flash_written=False)
(HERE/'sram-program-result.json').write_text(json.dumps(result,indent=2))
print(text)
raise SystemExit(r.returncode)
