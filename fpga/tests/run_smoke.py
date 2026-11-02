"""Portable RTL smoke checks: no synthesis, no hardware, no download."""
from pathlib import Path
import argparse,subprocess
P=Path(__file__).resolve().parent
S=P.parent/'source/fpga-capture-pipeline-20261004'

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--iverilog',default='iverilog')
    ap.add_argument('--vvp',default='vvp')
    a=ap.parse_args();out=P.parent/'test-output';out.mkdir(exist_ok=True)
    tests={
      'atomic':[S/'rtl'/n for n in ('afc03_capture_admission.sv','afc03_rgb_roi_probe.sv','afc03_camera_roi_tap.sv')]+[P/'tb_atomic.sv'],
      'video':[S/'board/fpga/uisrc/03_ip/vid_pipeline/sync_fifo_130.v',S/'rtl/afc03_stream_register.sv',P/'tb_video_stage.sv'],
    }
    for name,files in tests.items():
        output=out/(name+'.vvp')
        subprocess.run([a.iverilog,'-g2012','-s','tb','-o',str(output),*map(str,files)],check=True,timeout=60)
        subprocess.run([a.vvp,str(output)],check=True,timeout=60)
if __name__=='__main__':main()
