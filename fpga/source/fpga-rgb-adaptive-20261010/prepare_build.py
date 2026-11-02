from pathlib import Path
import shutil
H=Path(r'F:/AAA_FPGA/afc03-esp32-motor/fpga-rgb-adaptive-20261010');B=H.parent/'fpga-capture-pipeline-20261004'
for name in ('uisrc','al_ip'):
 shutil.copytree(B/'board/fpga'/name,H/'board/fpga'/name,dirs_exist_ok=True)
for p in (B/'board/fpga').rglob('*'):
 if p.is_file() and p.suffix in ('.vh','.svh'):
  dest=H/'sources'/p.relative_to(H.parent);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
s=(B/'build.py').read_text().replace("['integration','video-stage','atomic','overlap','read-write-progress']", "['integration','core']")
s=s.replace('checks={}', "checks={str(HERE/'rtl/spatial_mask.hex'):sha(HERE/'rtl/spatial_mask.hex')}")
(H/'build.py').write_text(s)
