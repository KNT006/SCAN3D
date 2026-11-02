from pathlib import Path
import sys,json,numpy as np,struct,zlib
H=Path(__file__).resolve().parent;sys.path.insert(0,str(H/'host'))
from row_results import Center,CandidateExtra,RowDone,ADAPTIVE_ALGORITHM,ProtocolError
from full_roi import commit_payload
from result_dma import parse_packet
from rgb_adaptive_strategy import threshold,validate_profile
header=json.loads((H.parent/'pc-adaptive-stripes-20261009/input-latest-new-item/position-034/A/frame.json').read_text());header['algorithm']=ADAPTIVE_ALGORITHM
context={k:v for k,v in header.items() if k in ('stream_epoch','background_generation','geometry','laser_id','laser_control','calibration','algorithm')};context['geometry']=dict(context['geometry'],roi_xyxy=[140,1121,880,1122])
rs=[]
for i in range(16):rs.extend([Center(1121,i,(150+i*30)*10,10,32768+25,149+i*30,151+i*30),CandidateExtra(1121,i,150+i*30,600)])
rs.append(RowDone(1121,16))
def run(records):return commit_payload(context,header['angle'],1,2,b''.join(r.encode() for r in records))
f=run(rs);assert len(f.centers)==16 and f.centers[15].peak_x==600
bad=[rs[:1]+rs[2:],rs[:2]+[rs[1]]+rs[2:],rs[:-1]+[RowDone(1121,15)],rs[:1]+[CandidateExtra(1121,1,150,600)]+rs[2:],rs[:1]+[CandidateExtra(1121,0,850,600)]+rs[2:]]
for records in bad:
 try:run(records)
 except ProtocolError:pass
 else:raise AssertionError('Invalid candidate records accepted')
for v,t in [(0,40),(12,25),(99,25),(100,25),(105,26),(130,33),(159,40),(160,40),(244,40),(245,40)]:assert threshold(np.full((9,9,3),v,np.uint8),4,4)['threshold']==t,(v,t)
# Complete real board-sim packets, CRC/padding/ABI validated by production parser.
packets=b''.join(int(x,16).to_bytes(16,'little') for x in (H/'dma-packets.txt').read_text().splitlines())
for at in (0,65536):
 p=packets[at:at+65536];w=struct.unpack_from('<32I',p);keys=('request_id','epoch','token','role','geometry','calibration','on_frame','bg_frame','records','rows','centers','crc32','cycles');e=dict(zip(keys,w[4:17]));e.update(size=w[20],roi_start=w[21],roi_end=w[22],bounds=w[23]);parse_packet(p,e,abi=0x60000)
 for offset in (128,65535):
  q=bytearray(p);q[offset]^=1
  try:parse_packet(q,e,abi=0x60000)
  except ValueError:pass
  else:raise AssertionError('Corruption accepted')
print('PROTOCOL_PASS capacity16, missing/duplicate/mismatched metadata, brightness boundaries, real DMA CRC/padding')
(H/'protocol-validation.json').write_text(json.dumps(dict(passed=True,negative_cases=9,max_candidates=16)))
