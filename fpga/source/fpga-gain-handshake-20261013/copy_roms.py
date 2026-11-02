from pathlib import Path
import shutil
H=Path(r'F:/AAA_FPGA/afc03-esp32-motor/fpga-gain-handshake-20261013');B=H.parent/'fpga-capture-pipeline-20261004'
for stage in ('syn_1','phy_1'):
 for p in (B/'board/fpga/imx415_pcie_4k_Runs'/stage).glob('*rom*.txt'):shutil.copy2(p,H/'board/fpga/imx415_pcie_4k_Runs'/stage/p.name)
