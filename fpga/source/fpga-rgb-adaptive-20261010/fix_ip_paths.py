from pathlib import Path
import re,shutil,os
H=Path(r'F:/AAA_FPGA/afc03-esp32-motor/fpga-rgb-adaptive-20261010')
for stage in ('syn_1','phy_1'):
 p=H/'board/fpga/imx415_pcie_4k_Runs'/stage/'imx415_pcie_4k.prj';s=p.read_text(encoding='latin1')
 def sub(m):
  path=Path(m[1]);return 'Path="'+os.path.relpath(path,p.parent).replace('\\','/')+'"'
 s=re.sub(r'Path="([^"]+)"',sub,s);p.write_text(s,encoding='latin1')
for name in ('uisrc','al_ip'):
 src=H.parent/'fpga-capture-pipeline-20261004/board/fpga'/name;dst=H/'sources/fpga-capture-pipeline-20261004/board/fpga'/name
 shutil.copytree(src,dst,dirs_exist_ok=True)
