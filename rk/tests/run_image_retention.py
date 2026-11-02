from pathlib import Path
import sys,runpy
root=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(root/'rk/rootfs/opt/afc03-scanner/scan3d'),str(root/'rk/rootfs/opt/afc03-scanner/fpga')]
runpy.run_path(str(root/'tools/image-retention/test_retention.py'),run_name='__main__')
