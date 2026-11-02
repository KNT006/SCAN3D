"""RK maintenance for the authorized new-B candidate, preserving driver state."""
from pathlib import Path
import subprocess, json, sys, time, urllib.request

JOB = Path('/userdata/afc03-scanner/jobs/new-B-ROM-20261028')
STATE = JOB/'before-hardware.json'
SERVICES = ['afc03-scanner', 'afc03-scan3d', 'afc03-camera']
DRIVERS = Path('/opt/afc03-drivers/20260929')
def run(args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()
def status(url):
    return json.load(urllib.request.urlopen(url, timeout=5))
def bar():
    return int(Path('/sys/bus/pci/devices/0000:21:00.0/resource').read_text().split()[0],16)

action = sys.argv[1]
if action == 'prepare':
    assert not STATE.exists(), 'Existing maintenance record must be preserved'
    st = status('http://127.0.0.1:8081/api/status')
    assert not any(st.get(k) for k in ('active_scans','active_jobs','active_calibrations')), st
    check = subprocess.check_output(['sha256sum','-c','SHA256SUMS'],cwd=DRIVERS,text=True)
    base = bar()
    params = {n:Path('/sys/module/anlogic_pci/parameters',n).read_text().strip()
              for n in ('poll_mode','enable_st_c2h_credit','desc_blen_max','poll_sleep_us','frame_desc_contiguous')}
    regs = {str(o):int(run(['busybox','devmem',str(base+o),'32']),16) for o in (0x60,0x90,0x98)}
    STATE.write_text(json.dumps(dict(status=st,parameters=params,registers=regs,driver_integrity=check),indent=2))
    run(['systemctl','stop',*SERVICES])
    run(['rmmod','milianke_v4l2'])
    run(['rmmod','anlogic_pci'])
    Path('/sys/bus/platform/drivers/rk-pcie/unbind').write_text('2a210000.pcie')
    print('PREPARED: services stopped, DMA unloaded, PCIe unbound',flush=True)
elif action == 'restore-camera':
    record = json.loads(STATE.read_text())
    Path('/sys/bus/platform/drivers/rk-pcie/bind').write_text('2a210000.pcie')
    for _ in range(30):
        if run(['lspci','-d','1edb:abcd']):
            break
        time.sleep(.5)
    else:
        raise RuntimeError('FPGA PCIe not enumerated')
    subprocess.check_call(['sha256sum','-c','SHA256SUMS'],cwd=DRIVERS)
    run(['insmod',str(DRIVERS/'anlogic_pci.ko'),*[n+'='+v for n,v in record['parameters'].items()]])
    run(['insmod',str(DRIVERS/'milianke_v4l2.ko')])
    base = bar()
    for o in (0x90,0x98,0x60):
        run(['busybox','devmem',str(base+o),'32',str(record['registers'][str(o)])])
    print(run(['env','PYTHONPATH=/opt/afc03-scanner/vendor','python3','/opt/afc03-scanner/fpga/boot_ready.py']))
    run(['systemctl','start','afc03-camera'])
    for _ in range(30):
        time.sleep(1)
        try:
            st = status('http://127.0.0.1:8080/status')
            if st.get('frames',0)>5 and st.get('raw_age',100)<1:
                break
        except Exception:
            pass
    else:
        raise RuntimeError('Camera did not recover')
    (JOB/'camera-after-hardware.json').write_text(json.dumps(st,indent=2))
    print('CAMERA_RESTORED',json.dumps(st),flush=True)
else:
    raise ValueError(action)
