"""Simulate shipped gain-handshake testbenches; never accesses hardware."""
from pathlib import Path
import argparse,subprocess,shutil,json
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--iverilog',default=shutil.which('iverilog'));p.add_argument('--vvp',default=shutil.which('vvp'));a=p.parse_args()
 if not a.iverilog or not a.vvp:raise SystemExit('Install Icarus Verilog or specify --iverilog and --vvp')
 src=ROOT/'source/fpga-gain-handshake-20261013';out=ROOT/'test-output/gain-handshake';out.mkdir(parents=True,exist_ok=True)
 rtl=src/'sources/fpga-capture-pipeline-20261004/board/fpga/uisrc/03_ip/ui_imx415_cfg'
 cdc=src/'sources/fpga-laser-20261001/rtl/afc03_cdc_snapshot.v'
 results=[]
 for kind,tb,extra,cases in [('transaction','tb_gain.sv',[],[f'+CASE={i}' for i in range(7)]),('pins','tb_gain_i2c.sv',[rtl/'ui_i2c.v',rtl/'ui_imx415_reg.v'],['+MODE=0','+MODE=1'])]:
  image=out/(kind+'.vvp');command=[a.iverilog,'-g2012','-s','tb','-o',str(image),str(rtl/'ui_cfg_imx415.v'),str(cdc),*[str(x) for x in extra],str(src/tb)]
  subprocess.run(command,check=True,capture_output=True,text=True)
  for case in cases:
   r=subprocess.run([a.vvp,str(image),case],capture_output=True,text=True,timeout=240)
   (out/(kind+case.replace('+','-').replace('=','-')+'.log')).write_text(r.stdout+r.stderr)
   passed=r.returncode==0 and ('PASS' in r.stdout)
   results.append(dict(kind=kind,case=case,passed=passed));print(json.dumps(results[-1]),flush=True)
   if not passed:raise RuntimeError(r.stdout+r.stderr)
 report=dict(passed=all(r['passed'] for r in results),runs=results,hardware_accessed=False)
 (out/'report.json').write_text(json.dumps(report,indent=2))
if __name__=='__main__':main()
