"""Operator-requested BOTH hold; renewal only, never restores a changed output."""
import json,signal,time,urllib.request
from pathlib import Path
from rk_motor import MotorBridge
PORT='/run/afc03-controller/control.sock'
status=Path('/run/afc03-laser-hold.json')
running=True
def stop(*_):
    global running
    running=False
signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
def idle():
    for url in ('http://127.0.0.1:8081/api/status','http://127.0.0.1:8081/api/fpga/status'):
        with urllib.request.urlopen(url,timeout=3) as r:s=json.load(r)
        if any(s.get(k) for k in ('active_scans','active_jobs','active_calibrations')):return False
        if any(r.get('status')=='running' for r in s.get('runs',[])):return False
    return True
count=0;armed=False
try:
    if not idle():raise RuntimeError('Acquisition active')
    b=MotorBridge(PORT)
    try:
        state=dict(x.split('=',1) for x in b.send('PULSE_STATE').split() if '=' in x)
        if state.get('moving')!='0' or state.get('armed')!='0':raise RuntimeError('Motor active')
        b.send('LED 0');print(b.send('LASER BOTH'),flush=True);armed=True
    finally:b.close()
    while running:
        if not idle():break
        b=MotorBridge(PORT)
        try:
            current=b.send('LASERSTATE')
            if 'A=1 B=1' not in current:break
            reply=b.send('LASERKEEP');count+=1
            status.write_text(json.dumps(dict(active=True,renewals=count,last_monotonic=time.monotonic(),reply=reply)))
        finally:b.close()
        for _ in range(50):
            if not running:break
            time.sleep(.1)
finally:
    if armed:
        try:
            b=MotorBridge(PORT)
            try:
                if 'A=1 B=1' in b.send('LASERSTATE'):b.send('LASER OFF')
            finally:b.close()
        except Exception:pass
    status.write_text(json.dumps(dict(active=False,renewals=count)))
