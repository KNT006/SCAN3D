"""Strict complete-frame diagnostic mailbox, not production point DMA."""
import time,struct,zlib
from result_dma import ResultDMA,ABI as DMA_ABI
from role_client import DiagnosticError,MAGIC,ABI,uint
class JobClient:
 def __init__(self,read,write):
  self.dma=None;self.read=read;self.write=write;self.base=0x2400;self.verify()
  self.next_id=max(1,self.read(self.base+0x84)+1)
 def verify(self):
  version=self.read(self.base+8)
  if self.read(self.base)!=MAGIC or version not in (ABI,0x00030000,DMA_ABI,0x00050000,0x00060000):raise DiagnosticError('Unsupported laser job ABI; no writes performed')
  if hasattr(self,'abi') and self.abi!=version:raise DiagnosticError('FPGA strategy changed during operation')
  self.abi=version
  self.new_stripes=version>=0x00030000
  self.spatial_candidates=version==0x00060000
  self.capture_overlap=version in (0x00050000,0x00060000)
  if self.spatial_candidates and (self.read(self.base+0x34),self.read(self.base+0x38))!=(0x9c744450,0x0046000b):raise DiagnosticError("Spatial ROM profile mismatch; no writes performed")
  self.transport="dma_result_queue_atomic_capture_v2" if self.capture_overlap else "dma_result_queue_v1" if version==DMA_ABI else "qualified_mailbox_not_result_dma"
 def close(self):
  if self.dma is not None:self.dma.close();self.dma=None
 def command(self,opcode,registers=None,timeout=2):
  self.verify();s=self.read(self.base+4)
  if not s&16 or s&9:raise DiagnosticError('Job mailbox unavailable')
  rid=self.next_id;self.next_id+=1
  if rid>=0xffffffff:raise DiagnosticError('Request IDs exhausted')
  for offset,value in (registers or {}).items():
   if offset not in range(0x10,0x34,4):raise ValueError('Forbidden register')
   self.write(self.base+offset,uint(value,32,'register'))
  self.write(self.base+12,rid);self.write(self.base+8,0x42470000|opcode)
  deadline=time.monotonic()+timeout
  while time.monotonic()<deadline:
   s=self.read(self.base+4)
   if s&12 or not s&16:raise DiagnosticError('Job reset/reject/watchdog; no automatic retry')
   if s&3==2:
    w=[self.read(self.base+0x80+i*4) for i in range(16)]
    if self.read(self.base+4)&31!=18 or self.read(self.base+0x80)!=w[0] or self.read(self.base+0x84)!=w[1]:raise DiagnosticError('Torn job reply')
    if w[1]==rid and w[0]&255==opcode:
     if (w[0]>>8)&255:raise DiagnosticError('Job result '+str((w[0]>>8)&255))
     return w
   time.sleep(.001)
  raise DiagnosticError('Job reply deadline; not retried')
 def wait_drained(self,timeout=12):
  deadline=time.monotonic()+timeout
  while time.monotonic()<deadline:
   w=self.command(1)
   if not w[0]&(1<<16):return w
   time.sleep(.001)
  raise DiagnosticError('Frame job has not drained; no retry')
 def run(self,*,role,epoch,geometry,calibration,token,width,height,roi,left,right,expected_bg,expected_on,during=None):
  if during is not None and not self.capture_overlap:raise DiagnosticError('Capture overlap requires job ABI5')
  if role not in (1,2):raise ValueError('Select A or B only')
  x0,y0,x1,y1=roi
  if not(0<=x0<x1<=width and x0%4==0 and 0<=y0<y1<=height and 0<=left<right<y1-y0):raise ValueError('Bad ROI')
  if (33 if self.spatial_candidates else 3)*(x1-x0)>2048 or y1-y0>1080:raise ValueError('Diagnostic result capacity exceeded')
  self.command(5,{0x10:epoch,0x14:geometry,0x18:calibration,0x1c:token,0x20:height<<16|width,
    0x24:y0<<16|x0,0x28:y1<<16|x1,0x2c:1+role*2,0x30:right<<16|left})
  self.in_flight=True;self.last_overlap_seconds=0
  try:
   if during is not None:
    overlap_started=time.perf_counter()
    during()
    self.last_overlap_seconds=time.perf_counter()-overlap_started
   w=self.wait_drained()
  finally:
   # A failed capture does not permit another command to reuse pinned slots.
   if during is not None:self.wait_drained()
   self.in_flight=False
  if w[0]>>16!=2 or w[10]:raise DiagnosticError('Frame rejected '+repr(w))
  if (w[2],w[8],w[9],w[11])!=(epoch,expected_on.source_frame,expected_bg.source_frame,token):raise DiagnosticError('Frame identity mismatch')
  if w[4]!=x1-x0 or w[3]!=w[4]+(2 if self.spatial_candidates else 1)*w[5] or not w[4]<=w[3]<=(33 if self.spatial_candidates else 3)*w[4]:raise DiagnosticError('Record counters inconsistent')
  receive_started=time.perf_counter()
  if self.abi in (DMA_ABI,0x00050000,0x00060000):
   if self.dma is None:self.dma=ResultDMA()
   q=self.command(7)
   if q[2:12]!=w[2:12] or q[0]>>16!=2:raise DiagnosticError('Result changed before DMA')
   expected=dict(request_id=q[1],epoch=epoch,token=token,role=role,geometry=geometry,calibration=calibration,
     on_frame=w[8],bg_frame=w[9],records=w[3],rows=w[4],centers=w[5],crc32=w[6],cycles=w[7],
     size=height<<16|width,roi_start=y0<<16|x0,roi_end=y1<<16|x1,bounds=right<<16|left)
   payload,self.last_dma_seconds=self.dma.receive(expected,abi=self.abi)
  else:
   payload=bytearray()
   for index in range(w[3]):
    q=self.command(6,{0x30:index*16})
    if q[2:12]!=w[2:12] or q[0]>>16!=2:raise DiagnosticError('Result changed while reading')
    payload.extend(struct.pack('<4I',*q[12:]))
   payload=bytes(payload)
  self.last_receive_seconds=time.perf_counter()-receive_started
  if zlib.crc32(payload)!=w[6]:raise DiagnosticError('CRC mismatch')
  return {'epoch':w[2],'records':w[3],'rows':w[4],'centers':w[5],'crc32':w[6],'cycles':w[7],
    'on_frame':w[8],'bg_frame':w[9],'token':w[11]},payload
