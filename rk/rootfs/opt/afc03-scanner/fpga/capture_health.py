"""Read-only video-path counters, using aligned 32-bit BAR loads."""
import ctypes,mmap,time
from pathlib import Path
REGS={'short_flush':0x68,'midframe_drop':0x94,'gate_drop':0x9c,'gate_pass':0xa0}
def snapshot(probe):
 with mmap.mmap(probe.fd,mmap.PAGESIZE,flags=mmap.MAP_SHARED,
                prot=mmap.PROT_READ|mmap.PROT_WRITE,offset=probe.base) as mem:
  result={name:ctypes.c_uint32.from_buffer(mem,offset).value for name,offset in REGS.items()}
 result['driver']={p.name:int(p.read_text()) for p in Path('/sys/module/milianke_v4l2/parameters').glob('capture_*')}
 return result

def next_frame_boundary(probe,timeout=.2,clock=time.monotonic,sleep=time.sleep):
 """Start both ARM commands early in a frame; exact marker checks still govern."""
 start=clock();previous=probe.read(0x34)
 while clock()-start<timeout:
  current=probe.read(0x34)
  if current!=previous:return dict(frame=current,wait_seconds=clock()-start)
  sleep(.001)
 raise RuntimeError('Camera frame counter stalled before ARM; no capture issued')
