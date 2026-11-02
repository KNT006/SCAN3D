"""Prepare a separately constrained dual-channel implementation."""
from pathlib import Path
import shutil,sys,xml.etree.ElementTree as ET
H=Path(__file__).resolve().parent;P=H.parent/'fpga-laser-20261001';L=P/'laser-board';OLD=H.parent/'fpga-strategy-20261003'
sys.path.insert(0,str(L))
import prepare_audit as previous
FIFOS=previous.FIFOS+[('result_dma/queue','u_ddr_test/u_ddr/dfi_clk','*/pcie_user_clk')]
def pointer_query(name,direction,kind):
    inst='u_laser/'+name;n=5 if name=='result_dma/queue' else 9 if name.endswith('capture/pixels') else 2
    if kind=='launch':return 'get_regs {'+' '.join(f'{inst}/{direction}_{e}[{i}]' for i in range(n) for e in ['gray','binary'])+'}'
    return 'get_regs {'+' '.join(f'{inst}/{direction}_gray_{kind}[{i}]' for i in range(n))+'}'
