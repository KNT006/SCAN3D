"""Prepare a new TD candidate directory, retaining the qualified input manifest."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
from generate import generate,FPGA,HERE

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 dest=a.output.resolve()
 generate()
 subprocess.run([sys.executable,str(FPGA/'prepare_project.py'),'--output',str(dest)],check=True)
 target=dest/'fpga-gain-handshake-20261013/rtl/afc03_laser_board_top.sv'
 old_hash=hashlib.sha256(target.read_bytes()).hexdigest()
 target.write_bytes((HERE/'afc03_laser_board_top.sv').read_bytes())
 # The qualified ROM source embeds an old machine path, outside .prj/.tcl relocation.
 core=dest/'fpga-gain-handshake-20261013/rtl/laser_full_row_core.v'
 text=core.read_text().replace('F:/AAA_FPGA/afc03-esp32-motor/fpga-rgb-adaptive-20261010/rtl/spatial_mask.hex',
    (dest/'fpga-gain-handshake-20261013/rtl/spatial_mask.hex').as_posix())
 core.write_text(text)
 # Same FIFO/reset implementation as BG, but a distinct instance needs its own constraints.
 cdc=FPGA/'source/fpga-gain-handshake-20261013/laser-cdc.sdc'
 lines=[line.replace('u_laser/bg/','u_laser/color/') for line in cdc.read_text().splitlines()
        if line.startswith('set_') and 'u_laser/bg/' in line]
 assert len(lines)==26,'Review changed baseline CDC constraints'
 derived='\n'.join(lines)+'\n'
 checked=(HERE/'color-cdc.sdc').read_text()
 assert '\n'.join(line for line in checked.splitlines() if line.startswith('set_'))+'\n'==derived
 target_cdc=dest/'fpga-gain-handshake-20261013/color-cdc.sdc'
 target_cdc.write_text(checked)
 for stage in ('syn_1','phy_1'):
  cfg=dest/'fpga-gain-handshake-20261013/board/fpga/imx415_pcie_4k_Runs'/stage/'settings.cfg'
  cfg.write_text(cfg.read_text()+'\nlappend SDCList {'+target_cdc.as_posix()+'}\n')
 (dest/'color-cache-candidate.json').write_text(json.dumps(dict(qualified_top_sha256=old_hash,
    candidate_top_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
    candidate=True,qualified_manifest_unchanged=True,new_bitstream_validated=False),indent=2))
 print('Candidate prepared:',dest)
if __name__=='__main__':main()
