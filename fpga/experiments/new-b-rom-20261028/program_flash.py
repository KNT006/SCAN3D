"""Program the qualified new-B bit after exact board/software candidate checks."""
from pathlib import Path
import hashlib, json, subprocess, time

HERE = Path(__file__).resolve().parent
candidate = json.loads((HERE / 'candidate.json').read_text())
validation = json.loads((HERE / 'native-static-status.json').read_text())
backup = json.loads((HERE / 'flash-backup.json').read_text())
bit = Path(candidate['bit'])
assert candidate['timing_qualified']
assert hashlib.sha256(bit.read_bytes()).hexdigest() == candidate['sha256']
assert validation['passed'] and validation['status'] == 'complete'
for laser in ('A', 'B'):
    check = validation['lasers'][laser]['comparison']
    assert check['passed'] and check['exact_rational_and_metadata']
    assert check['mismatch_rows'] == 0 and check['centers'] > 0
assert hashlib.sha256(Path(backup['path']).read_bytes()).hexdigest() == backup['sha256']
tcl = HERE / 'program-flash.tcl'
tcl.write_text('if {[catch {\nconnect_cable -host_name 127.0.0.1:5555\ndownload -bit {' + bit.as_posix() + '} -mode program_spi -v -spd 6 -cable 0\n} reason]} {puts stderr $reason; exit 1}\nexit 0\n')
started = time.time()
logfile = HERE / 'program-flash.log'
with logfile.open('w') as output:
    result = subprocess.run(['D:/Anlogic/TD_6.2.1_Release_6.2.175.876/bin/bw_commands_prompt.exe', tcl.as_posix()], stdout=output, stderr=subprocess.STDOUT)
log = logfile.read_text(errors='replace')
passed = (result.returncode == 0 and 'Chip validation success: PH1A90' in log
          and 'finish command "download ' in log and 'SPI flash Page program and verify' in log
          and not any(term in log.lower() for term in ('error:', 'failed', 'mismatch')))
record = dict(passed=passed, exit_code=result.returncode, seconds=time.time()-started,
              bit_sha256=candidate['sha256'], flash_written=passed,
              cold_boot_tested=False, object_scan_validated=False,
              validation_scope='Exact A/B FPGA candidate comparison; empty turntable, not object accuracy')
(HERE / 'program-flash-result.json').write_text(json.dumps(record, indent=2))
print(json.dumps(record))
assert passed, log
