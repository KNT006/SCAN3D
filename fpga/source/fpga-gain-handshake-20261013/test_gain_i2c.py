"""Pin-level test using the unchanged production I2C master and camera ROM."""
from pathlib import Path
import subprocess,hashlib,json,time
H=Path(__file__).resolve().parent
B=H.parent/'capture-repair-20260928/tools/bin'
D=H/'sources/fpga-capture-pipeline-20261004/board/fpga/uisrc/03_ip/ui_imx415_cfg'
sources=[D/'ui_cfg_imx415.v',D/'ui_i2c.v',D/'ui_imx415_reg.v',
 H/'sources/fpga-laser-20261001/rtl/afc03_cdc_snapshot.v',H/'tb_gain_i2c.sv']
compiled=subprocess.run([str(B/'iverilog.exe'),'-g2012','-s','tb','-o',str(H/'gain-i2c.vvp'),*[str(p) for p in sources]],capture_output=True,text=True)
(H/'gain-i2c-compile.log').write_text(compiled.stdout+compiled.stderr)
assert compiled.returncode==0,compiled.stderr
start=time.time();results=[];logs=[]
for mode in [0,1]:
 t=time.time()
 r=subprocess.run([str(B/'vvp.exe'),str(H/'gain-i2c.vvp'),f'+MODE={mode}'],capture_output=True,text=True,timeout=240)
 logs.append(r.stdout+r.stderr)
 result=dict(mode=mode,passed=r.returncode==0 and f'PASS_I2C_ALL cases=5 mode={mode}' in r.stdout,seconds=time.time()-t)
 results.append(result);print(json.dumps(result),flush=True)
(H/'gain-i2c.log').write_text('\n'.join(logs))
report=dict(passed=all(r['passed'] for r in results),modes=results,cases_per_mode=5,
 seconds=time.time()-start,source='production I2C master; SCL/SDA-decoding ACK/NACK slave',
 sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
(H/'gain-i2c-validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report));assert report['passed']
