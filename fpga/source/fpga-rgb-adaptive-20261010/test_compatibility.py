from pathlib import Path
import sys,json,struct,zlib
H=Path(r'F:/AAA_FPGA/afc03-esp32-motor/fpga-rgb-adaptive-20261010');sys.path.insert(0,str(H/'host'))
from row_results import *
from full_roi import commit_payload
from result_dma import parse_packet
old=H.parent/'fpga-capture-pipeline-20261004/dma-packets.txt';data=b''.join(int(x,16).to_bytes(16,'little') for x in old.read_text().splitlines())
for at in (0,65536):
 p=data[at:at+65536];w=struct.unpack_from('<32I',p);keys=('request_id','epoch','token','role','geometry','calibration','on_frame','bg_frame','records','rows','centers','crc32','cycles');expected=dict(zip(keys,w[4:17]));expected.update(size=w[20],roi_start=w[21],roi_end=w[22],bounds=w[23]);payload=parse_packet(p,expected,abi=0x50000)
 assert len(payload)==16*16
h=json.loads((H.parent/'pc-adaptive-stripes-20261009/input-latest-new-item/position-034/A/frame.json').read_text());c={k:v for k,v in h.items() if k in ('stream_epoch','background_generation','geometry','laser_id','laser_control','calibration','algorithm')};c['algorithm']='fpga-brightcore-width100-signal40-v1';c['geometry']=dict(c['geometry'],roi_xyxy=[140,1121,880,1122]);f=commit_payload(c,h['angle'],1,2,Center(1121,0,4000,10,0x8028,399,401).encode()+RowDone(1121,1).encode());assert f.centers[0].num==4000
(H/'compatibility-validation.json').write_text(json.dumps(dict(passed=True,old_abi5_packets=2,old_row_receiver=True)));print('ABI5_COMPATIBILITY_PASS')
