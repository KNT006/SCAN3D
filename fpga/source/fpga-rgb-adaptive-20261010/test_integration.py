from pathlib import Path
import sys,subprocess,json,hashlib
H=Path(__file__).resolve().parent;OLD=H.parent/'fpga-strategy-20261003';P=H.parent/'fpga-laser-20261001'
sys.path.insert(0,str(P/'laser-board'))
from sources import sources
ss=[H/'rtl'/p.name if (H/'rtl'/p.name).exists() else p for p in sources()]+[H/'rtl/afc03_result_dma.sv']
ss.append(H/'tb_board.sv')
BIN=H.parent/'capture-repair-20260928/tools/bin'
r=subprocess.run([str(BIN/'iverilog.exe'),'-g2012','-s','tb','-o',str(H/'test.vvp'),*map(str,ss)],capture_output=True,text=True)
(H/'integration-compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr
r=subprocess.run([str(BIN/'vvp.exe'),str(H/'test.vvp')],cwd=H,capture_output=True,text=True,timeout=180)
(H/'integration-test.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
data=b''.join(int(x,16).to_bytes(16,'little') for x in (H/'dma-packets.txt').read_text().splitlines())
assert len(data)==2*65536
import struct,zlib
records=[];cur=None
for line in (H/'board-records.txt').read_text().splitlines():
 a=line.split()
 if a[0]=='FRAME':cur=bytearray();records.append(cur)
 else:cur.extend(int(a[1],16).to_bytes(16,'little'))
for i in range(2):
 p=data[i*65536:(i+1)*65536];h=struct.unpack('<32I',p[:128]);payload=p[128:128+16*h[12]]
 assert h[:4]==(0x51444d41,0x10000,65536,128) and h[5:10]==(7,101+i,1+i,31,11)
 assert h[12:15]==(24,8,8) and h[15]==zlib.crc32(payload) and h[17:20]==(0,0x60000,0)
 assert h[20:24]==(16<<16|16,4,16<<16|12,14<<16|1)
 assert payload==records[i] and not any(p[128+len(payload):]) and not any(h[24:])
report=dict(passed=True,frames=2,packet_bytes=65536,exact_csr_dma_match=True,backpressure=True,overwrite_rejected=True,failed_frame_dma_rejected=True,sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in ss})
(H/'integration-validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))

