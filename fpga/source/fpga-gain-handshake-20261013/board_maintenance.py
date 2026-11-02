"""Authorized FPGA maintenance; preserve current drivers/settings. No motion commands."""
from pathlib import Path
import sys,json,time
H=Path(__file__).resolve().parent
sys.path.insert(0,str(H.parent/'material-recognition-20261011'))
from rk_connection import connect,run
action=sys.argv[1];label=sys.argv[2] if len(sys.argv)>2 else 'sram'
assert action in ('prepare','restore') and label in ('sram','flash')
s=connect();saved=H/('board-before-'+label+'.json')
services='afc03-scanner afc03-scan3d afc03-camera'
def cmd(c,timeout=30):return run(s,c,timeout)
def bar():return int(cmd('head -1 /sys/bus/pci/devices/0000:21:00.0/resource').split()[0],16)
try:
 if action=='prepare':
  assert not saved.exists(),'Preserve existing maintenance record; do not overwrite'
  st=json.loads(cmd('curl -fsS --max-time 4 http://127.0.0.1:8081/api/status'))
  assert not any(st.get(k) for k in ('active_scans','active_jobs','active_calibrations')),'Scanner busy'
  integrity=cmd('cd /opt/afc03-drivers/20260929 && sha256sum -c SHA256SUMS')
  b=bar();regs={str(o):int(cmd(f'busybox devmem {b+o} 32').strip(),16) for o in (0x60,0x90,0x98)}
  params={n:cmd(f'cat /sys/module/anlogic_pci/parameters/{n}').strip() for n in ('poll_mode','enable_st_c2h_credit','desc_blen_max','poll_sleep_us','frame_desc_contiguous')}
  saved.write_text(json.dumps(dict(status=st,registers=regs,parameters=params,driver_integrity=integrity),indent=2))
  cmd('systemctl stop '+services)
  cmd('rmmod milianke_v4l2 && rmmod anlogic_pci')
  cmd('echo 2a210000.pcie > /sys/bus/platform/drivers/rk-pcie/unbind')
  print('Prepared: capture stopped, DMA unloaded, PCIe unbound')
 else:
  record=json.loads(saved.read_text())
  cmd('echo 2a210000.pcie > /sys/bus/platform/drivers/rk-pcie/bind')
  for _ in range(20):
   if cmd('lspci -d 1edb:abcd').strip():break
   time.sleep(.5)
  else:raise RuntimeError('FPGA PCIe not enumerated')
  cmd('cd /opt/afc03-drivers/20260929 && sha256sum -c SHA256SUMS')
  opts=' '.join(n+'='+v for n,v in record['parameters'].items())
  cmd('insmod /opt/afc03-drivers/20260929/anlogic_pci.ko '+opts)
  cmd('insmod /opt/afc03-drivers/20260929/milianke_v4l2.ko')
  b=bar()
  for o in (0x90,0x98,0x60):cmd(f'busybox devmem {b+o} 32 {record["registers"][str(o)]}')
  cmd('PYTHONPATH=/opt/afc03-scanner/vendor /usr/bin/python3 /opt/afc03-scanner/fpga/boot_ready.py')
  cmd('systemctl start '+services)
  for _ in range(30):
   time.sleep(1)
   try:
    st=json.loads(cmd('curl -fsS --max-time 2 http://127.0.0.1:8080/status'))
    if st.get('frames',0)>5 and st.get('raw_age',100)<1:break
   except RuntimeError:pass
  else:raise RuntimeError('Camera did not recover')
  (H/('board-restored-'+label+'.json')).write_text(json.dumps(st,indent=2));print(json.dumps(st))
finally:s.close()
