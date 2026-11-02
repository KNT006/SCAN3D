from pathlib import Path
import sys,json,urllib.request
sys.path[:0]=['/opt/afc03-scanner/fpga','/opt/afc03-scanner/vendor','/opt/afc03-motor']
from stationary_strategy import Probe,BackgroundMMIO
p=Probe()
try:
 m=BackgroundMMIO(p);print(json.dumps(dict(job_abi=hex(m.read(0x2408)),job_magic=hex(m.read(0x2400)),job_status=hex(m.read(0x2404)))))
finally:p.close()
for url in ('http://127.0.0.1:8081/api/status','http://127.0.0.1:8080/status'):
 try:
  d=json.load(urllib.request.urlopen(url,timeout=3));print(url,json.dumps(d)[:1800])
 except Exception as e:print(type(e).__name__,str(e))
