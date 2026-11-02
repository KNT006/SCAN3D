"""Fail closed unless both scanner stores are on the configured writable SD."""
import json,os,shutil,subprocess
from pathlib import Path
CONFIG=Path('/etc/afc03-sd-storage.json')
def inspect():
    cfg=json.loads(CONFIG.read_text())
    device=Path('/dev/disk/by-uuid')/cfg['uuid']
    actual=device.resolve(strict=True)
    parent=subprocess.check_output(['lsblk','-n','-o','PKNAME',str(actual)],text=True).strip()
    sysdev=Path('/sys/class/block')/parent/'device'
    if (sysdev/'type').read_text().strip()!='SD':raise RuntimeError('Configured storage is not SD')
    if (sysdev/'cid').read_text().strip()!=cfg['cid']:raise RuntimeError('SD identity mismatch')
    for dest,subdir in [(cfg['mount'],None),*cfg['bindings'].items()]:
        record=json.loads(subprocess.check_output(['findmnt','-J','-T',dest,'-o','TARGET,SOURCE,FSTYPE,OPTIONS'],text=True))['filesystems'][0]
        source=record['source'].split('[',1)[0]
        if record['target']!=dest or Path(source).resolve()!=actual:raise RuntimeError('SD mount missing: '+dest)
        if record['fstype']!='ext4' or 'rw' not in record['options'].split(','):raise RuntimeError('SD mount not writable: '+dest)
        if subdir and not os.path.samefile(dest,str(Path(cfg['mount'])/subdir)):raise RuntimeError('Wrong SD directory: '+dest)
        if os.stat(dest).st_dev!=os.stat(cfg['mount']).st_dev:raise RuntimeError('Internal disk fallback refused')
    usage=shutil.disk_usage(cfg['mount'])
    return dict(sd_configured=True,medium='SD',filesystem='ext4',mount=cfg['mount'],uuid=cfg['uuid'],
                path='/userdata/afc03-scanner/jobs',free_gib=round(usage.free/1024**3,2),total_gib=round(usage.total/1024**3,2))
def status():
    try:return inspect()
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as e:
        return dict(sd_configured=False,medium='unavailable',path='/userdata/afc03-scanner/jobs',error=str(e))
if __name__=='__main__':print(json.dumps(inspect(),indent=2))
