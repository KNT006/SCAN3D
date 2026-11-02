"""Finish the explicitly authorized Flash deployment and preserve acceptance evidence."""
from pathlib import Path
import datetime, hashlib, json, subprocess, sys, time
H=Path(__file__).resolve().parent
sys.path.insert(0,str(H.parent/'material-recognition-20261011'))
from rk_connection import connect,run
def save(name,obj):
    (H/name).write_text(json.dumps(obj,indent=2),encoding='utf-8')
def stamp():return datetime.datetime.now().astimezone().isoformat()
try:
    print('Waiting for Flash program/verify result',flush=True)
    deadline=time.monotonic()+3600
    while not (H/'program-flash-result.json').exists():
        if time.monotonic()>deadline:raise TimeoutError('Programming result missing; no interruption sent to programmer')
        time.sleep(2)
    flash=json.loads((H/'program-flash-result.json').read_text())
    q=json.loads((H/'qualified.json').read_text())
    assert flash['passed'] and flash['sha256']==q['sha256'],'Flash verification failed'
    q.update(flash_written=True,cold_boot_tested=False);save('qualified.json',q)
    save('deployment-status.json',dict(stage='flash_verified_restoring',timestamp=stamp(),flash_verified=True,cold_boot_tested=False))
    print('Flash verified; restoring capture',flush=True)
    subprocess.run([sys.executable,str(H/'board_maintenance.py'),'restore','flash'],check=True)
    s=connect()
    remote='/root/deploy/gain-handshake-20261013/flash-validation'
    local=H/'board-inspection'/'flash-validation';local.mkdir(exist_ok=True)
    try:
        print('Running 20 post-programming gain/image checks',flush=True)
        output=run(s,'PYTHONPATH=/opt/afc03-scanner/vendor /usr/bin/python3 /root/deploy/gain-handshake-20261013/validate_board_gain.py --count 20 --out '+remote,90)
        (local/'run.log').write_text(output)
        f=s.open_sftp()
        try:
            for name in f.listdir(remote):f.get(remote+'/'+name,str(local/name))
        finally:f.close()
        raw=run(s,'PYTHONPATH=/opt/afc03-scanner/vendor:/opt/afc03-scanner/fpga /usr/bin/python3 /opt/afc03-scanner/fpga/rk_laser_ready.py')
        (local/'ddr.json').write_text(raw)
        services=run(s,'systemctl is-active afc03-scanner afc03-scan3d afc03-camera')
        assert services.split()==['active','active','active']
    finally:s.close()
    v=json.loads((local/'validation.json').read_text());d=json.loads((local/'ddr.json').read_text())
    assert v['passed'] and len(v['records'])==20
    assert d['legacy_before']['bridge_ready'] and d['legacy_before']['init_advisory']['control_ready'] and not any(d['legacy_before'][k] for k in ('timeout','reset_held','rejected'))
    result=dict(stage='complete',passed=True,timestamp=stamp(),sha256=q['sha256'],flash_verified=True,flash_seconds=flash['seconds'],gain_switches_before_flash=100,gain_switches_after_flash=20,capture_restored=True,services_active=True,gain_restored=v['restored_gain'],cold_boot_tested=False,motor_operations=False,laser_operations=False,scope='Gain I2C handshake repair only; no RK/ESP32 production code or scan algorithm changes',limitations=['No full scan or laser-switching test: controller serial absent.','Power-cycle acceptance remains pending.'],evidence={str(p.relative_to(H)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [H/'hardware-validation.json',H/'program-flash-result.json',local/'validation.json',local/'ddr.json']})
    reload_path=H/'postflash-sram-reload.json'
    if reload_path.exists():
        reload_result=json.loads(reload_path.read_text())
        assert reload_result['passed'] and reload_result['sha256']==q['sha256']
        result['postflash_sram_reload']=reload_result
        result['running_source']='JTAG SRAM reload of same verified Flash candidate; not a Flash boot test'
        result['evidence']['postflash-sram-reload.json']=hashlib.sha256(reload_path.read_bytes()).hexdigest()
    save('deployment-status.json',result)
    notes=H/'RELEASE-NOTES.txt'
    with notes.open('a',encoding='utf-8') as f:
        f.write('\nBoard deployment update — '+stamp()+'\nTemporary JTAG load passed 100 alternating gain transactions with fresh RGB\nbrightness verification. Flash programmed and verified; capture restored.\nAfter Flash programming, PCIe did not enumerate until the same candidate\nwas reloaded into SRAM through JTAG. This is NOT Flash-boot validation.\n20 further gain/image checks passed, DDR health and all three services normal.\nOriginal camera gain restored. No motor or lighting commands were issued.\nESP32 serial was unavailable: static laser A/B extraction was not rerun.\nNo claim of a fresh complete scan or cold-boot acceptance; power-cycle pending.\nSee deployment-status.json and board-inspection/ for evidence.\n')
    print(json.dumps(result),flush=True)
except Exception as e:
    save('deployment-status.json',dict(stage='needs_attention',passed=False,timestamp=stamp(),error=repr(e),flash_result_exists=(H/'program-flash-result.json').exists()))
    raise
