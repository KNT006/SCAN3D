"""RK-only, bounded one-ROI same-frame diagnostic. Default status is read-only.

Capture explicitly arms a four-pixel test marker and BRAM snapshot. It never
controls motors/lasers, changes camera settings, or falls back to another frame.
"""
import argparse
import ctypes
import hashlib
import json
import mmap
import os
from pathlib import Path
import secrets
import struct
import sys
import time
from urllib.request import Request, urlopen

MAGIC, ABI = 0x31544752, 0x00010000
ARM, CANCEL, WINDOW = 0x52470001, 0x52470000, 0x2100
FAULTS = {0:'none',1:'invalid_configuration',2:'line_or_coordinate_error',
          3:'storage_overflow',4:'unexpected_sof',5:'incomplete_capture',6:'stream_reset'}


def flags_dict(flags):
    return dict(flags=flags, waiting=bool(flags&1), active=bool(flags&2),
                done=bool(flags&4), fault_present=bool(flags&8),
                rejected=bool(flags&16), read_valid=bool(flags&32))


class Probe:
    def __init__(self, bdf=None, sysfs_root=Path('/sys/bus/pci/devices')):
        if sys.byteorder != 'little':
            raise RuntimeError('Only little-endian host MMIO is supported')
        nodes = [sysfs_root/bdf] if bdf else list(sysfs_root.iterdir())
        found = []
        for node in nodes:
            try:
                if int((node/'vendor').read_text(),16)==0x1edb and int((node/'device').read_text(),16)==0xabcd:
                    found.append(node)
            except (OSError,ValueError):
                pass
        if len(found)!=1:
            raise RuntimeError('Expected exactly one 1edb:abcd PCIe device; found %d' % len(found))
        self.node=found[0]
        base,end,flags=[int(v,16) for v in (self.node/'resource').read_text().splitlines()[0].split()]
        if not base or not (flags&0x200) or end-base+1<WINDOW+0x100:
            raise RuntimeError('BAR0 is not a sufficiently large assigned memory resource')
        self.base=base
        # Map only the 4 KiB page containing probe registers. Native aligned
        # uint32 stores guarantee full WSTRB; byte-slice stores are forbidden.
        page_offset=WINDOW&~(mmap.PAGESIZE-1)
        self.offset=WINDOW-page_offset
        self.fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
        try:
            self.mem=mmap.mmap(self.fd,mmap.PAGESIZE,flags=mmap.MAP_SHARED,
                              prot=mmap.PROT_READ|mmap.PROT_WRITE,offset=base+page_offset)
        except BaseException:
            os.close(self.fd);raise
        try:
            self.abi=self.read(8)
            if self.read(0)!=MAGIC or self.abi not in (ABI,0x00020000):
                raise RuntimeError('RGB ROI candidate magic/ABI absent; no register writes performed')
        except BaseException:
            self.close();raise

    def close(self):
        self.mem.close();os.close(self.fd)

    def read(self, offset):
        if offset&3 or not 0<=offset<0x100:raise ValueError('Unaligned/out-of-window MMIO read')
        return ctypes.c_uint32.from_buffer(self.mem,self.offset+offset).value

    def write(self, offset, value):
        if offset not in (0x08,0x0c,0x10,0x14,0x28) or not 0<=value<=0xffffffff:
            raise ValueError('Forbidden ROI MMIO write')
        ctypes.c_uint32.from_buffer(self.mem,self.offset+offset).value=value
        self.read(4) # flush posted write before continuing

    def status(self):
        return probe_status(self)


def probe_status(probe):
    status=flags_dict(probe.read(4))
    a,b,dimensions=probe.read(0x10),probe.read(0x14),probe.read(0x20)
    fault=probe.read(0x24)
    status.update(token=probe.read(0x0c),frame_id=probe.read(0x18),
                  words_written=probe.read(0x1c),capacity_words=probe.read(0x28),
                  roi=[a&0x1fff,(a>>16)&0x1fff,b&0x1fff,(b>>16)&0x1fff],
                  image_size=[dimensions&0x1fff,(dimensions>>16)&0x1fff],
                  fault=fault,fault_name=FAULTS.get(fault,'unknown'),
                  read_index=probe.read(0x2c),expected_words=probe.read(0x30),
                  current_frame_counter=probe.read(0x34))
    return status


class CameraAPI:
    def __init__(self, base='http://127.0.0.1:8080', timeout=3.0):
        self.base,self.timeout=base.rstrip('/'),timeout

    def request(self, path, obj=None, binary=False):
        data=None if obj is None else json.dumps(obj).encode()
        req=Request(self.base+path,data=data,headers={} if data is None else {'Content-Type':'application/json'})
        with urlopen(req,timeout=self.timeout) as response:
            limit=1920*1080*3+4096 if binary else 65536
            length=int(response.headers.get('Content-Length','-1'))
            if not 0<=length<=limit:raise RuntimeError('HTTP response has invalid or excessive size')
            body=response.read(length+1)
            if len(body)!=length:raise RuntimeError('HTTP response length mismatch')
            return (body,dict(response.headers)) if binary else json.loads(body)


def validate_roi(roi, width, height, capacity_words):
    if len(roi)!=4 or any(type(v) is not int for v in roi):raise ValueError('ROI requires four integers')
    x0,y0,x1,y1=roi
    if not 0<=x0<x1<=width or not 0<=y0<y1<=height:
        raise ValueError('ROI lies outside native image coordinates')
    if x0%4 or x1%4:raise ValueError('ROI x0 and x1 must align to four pixels')
    if y0==0 and x0<4:raise ValueError('ROI must exclude the four diagnostic marker pixels')
    words=(x1-x0)//4*(y1-y0)
    if words>capacity_words:raise ValueError('ROI exceeds BRAM capacity: %d > %d words' %(words,capacity_words))
    return words


def parse_ppm(data):
    # Service format is deliberately exact. Do not use a whitespace-skipping
    # image parser that could eat a valid leading RGB byte such as 0x0a/0x20.
    parts=data.split(b'\n',3)
    if len(parts)!=4 or parts[0]!=b'P6' or parts[2]!=b'255':
        raise RuntimeError('Unexpected lossless PPM header')
    try:width,height=[int(v) for v in parts[1].split()]
    except (ValueError,TypeError):raise RuntimeError('Malformed PPM dimensions')
    rgb=parts[3]
    if width!=1920 or height!=1080 or len(rgb)!=width*height*3:
        raise RuntimeError('Unexpected raw image dimensions or byte length')
    return width,height,rgb


def roi_from_raw(rgb,width,roi):
    x0,y0,x1,y1=roi
    return b''.join(rgb[(y*width+x0)*3:(y*width+x1)*3] for y in range(y0,y1))


def decode_snapshot(raw_words):
    if len(raw_words)%16:raise ValueError('Snapshot must contain complete 128-bit beats')
    words=struct.unpack('<%dI'%(len(raw_words)//4),raw_words)
    if any(word>>24 for word in words):raise RuntimeError('Nonzero 32-bit pixel padding in FPGA snapshot')
    return bytes(component for word in words for component in ((word>>16)&255,(word>>8)&255,word&255))


def compare_rgb(actual,expected,roi):
    if len(actual)!=len(expected):raise RuntimeError('ROI byte count mismatch')
    differences=[i for i,(a,b) in enumerate(zip(actual,expected)) if a!=b]
    width=roi[2]-roi[0]
    return dict(passed=not differences,compared_bytes=len(actual),compared_pixels=len(actual)//3,
                mismatched_bytes=len(differences),mismatched_pixels=len({i//3 for i in differences}),
                max_absolute_error=max((abs(a-b) for a,b in zip(actual,expected)),default=0),
                first_mismatches=[dict(x=roi[0]+(i//3)%width,y=roi[1]+(i//3)//width,
                                       channel='RGB'[i%3],fpga=actual[i],rk=expected[i])
                                  for i in differences[:16]])


def check_snapshot(status,token,roi,expected_words,dimensions=None,frame_id=None):
    if status['waiting'] or status['active'] or not status['done'] or status['fault'] or status['rejected']:
        raise RuntimeError('FPGA snapshot incomplete or faulted: '+json.dumps(status))
    if status['token']!=token or status['roi']!=list(roi):raise RuntimeError('FPGA token/ROI changed concurrently')
    if status['words_written']!=expected_words or status['expected_words']!=expected_words:
        raise RuntimeError('FPGA snapshot word count mismatch')
    if dimensions is not None and status['image_size']!=list(dimensions):
        raise RuntimeError('FPGA / RK image dimensions disagree')
    if frame_id is not None and status['frame_id']!=frame_id:
        raise RuntimeError('FPGA captured frame id changed concurrently')


def read_snapshot(probe,words,timeout_s=10.0):
    deadline=time.monotonic()+timeout_s
    result=bytearray()
    for index in range(words):
        if time.monotonic()>=deadline:raise TimeoutError('Indexed BRAM read exceeded deadline')
        probe.write(0x28,index)
        item_deadline=min(deadline,time.monotonic()+0.1)
        while time.monotonic()<item_deadline:
            status=flags_dict(probe.read(4))
            if status['fault_present'] or status['rejected'] or not status['done']:
                raise RuntimeError('FPGA fault during indexed BRAM read')
            if status['read_valid'] and probe.read(0x2c)==index:break
        else:raise TimeoutError('BRAM read did not acknowledge index %d'%index)
        result.extend(struct.pack('<4I',*(probe.read(0x40+4*i) for i in range(4))))
    return bytes(result)


def allocate_token(path,known_tokens):
    """Call only while holding the process lock. No reuse within this RK boot."""
    previous=int(path.read_text()) if path.exists() else 0
    last=max([previous]+[int(v or 0) for v in known_tokens])
    if not 0<=last<0xffffffff:raise RuntimeError('Diagnostic token space exhausted or state file invalid')
    token=last+1 if last else secrets.randbelow(0x7ffffffe)+1
    temporary=path.with_suffix('.tmp')
    temporary.write_text(str(token)+'\n');os.replace(temporary,path)
    return token


def scanner_idle(base):
    state=CameraAPI(base).request('/api/status')
    keys=('active_scans','active_jobs','active_calibrations')
    if any(k not in state for k in keys):raise RuntimeError('Cannot verify scanner idle: status fields missing')
    if any(state[k] for k in keys):raise RuntimeError('Scanner is busy; diagnostic marker is forbidden during scanning')
    return {k:state[k] for k in keys}


def capture_one(probe,api,roi,output,wait_s,scanner_base,token_path):
    report=dict(passed=False,kind='rgb_roi_same_frame_diagnostic',roi=list(roi),
                created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                motor_operations=False,laser_operations=False,flash_modified=False,
                stage='preflight',cleanup_errors=[])
    generation=None;owns_probe=False
    output.mkdir(parents=True,exist_ok=False)
    started=time.monotonic()
    try:
        report['scanner_idle']=scanner_idle(scanner_base)
        previous=probe.status();report['fpga_before']=previous
        if previous['waiting'] or previous['active']:raise RuntimeError('Another FPGA ROI capture is active')
        service=api.request('/diagnostic/roi/status');report['camera_before']=service
        if service['state'] in ('waiting','copying','ready'):raise RuntimeError('Another camera diagnostic is pending or retained')
        width,height=int(service['width']),int(service['height'])
        words=validate_roi(roi,width,height,previous['capacity_words'])
        token=allocate_token(token_path,[previous['token'],service.get('token')])
        report.update(token=token,expected_words=words,native_size=[width,height])
        report['stage']='arm_camera'
        armed=api.request('/diagnostic/roi/arm',{'token':token,'timeout_s':wait_s})
        generation=armed['generation'];report['camera_arm']=armed
        if armed['state']!='waiting' or armed['token']!=token:raise RuntimeError('Unexpected camera arm acknowledgement')
        report['stage']='arm_fpga'
        owns_probe=True
        probe.write(8,CANCEL)
        probe.write(0x0c,token)
        probe.write(0x10,roi[0]|(roi[1]<<16));probe.write(0x14,roi[2]|(roi[3]<<16))
        probe.write(8,ARM)
        report['stage']='await_same_frame'
        deadline=time.monotonic()+wait_s
        while time.monotonic()<deadline:
            fpga=probe.status();camera=api.request('/diagnostic/roi/status')
            report['fpga_capture'],report['camera_capture']=fpga,camera
            if fpga['fault'] or fpga['rejected']:raise RuntimeError('FPGA capture fault: '+json.dumps(fpga))
            if camera['generation']!=generation or camera['token']!=token or camera['stream_id']!=armed['stream_id']:
                raise RuntimeError('Camera diagnostic identity changed')
            if camera['state'] in ('error','expired','invalid','cancelled','idle'):
                raise RuntimeError('Camera diagnostic unavailable: '+json.dumps(camera))
            if fpga['done'] and camera['state']=='ready':break
            time.sleep(0.02)
        else:raise TimeoutError('No matching FPGA+RK frame before deadline; no alternate frame used')
        check_snapshot(fpga,token,roi,words,[width,height])
        report['stage']='read_raw_frame'
        ppm,headers=api.request('/diagnostic/roi/frame?generation='+str(generation),binary=True)
        (output/'same-frame.ppm').write_bytes(ppm)
        report['raw_http_headers']=headers
        normalized={k.lower():v for k,v in headers.items()}
        if int(normalized.get('x-roi-token','-1'))!=token or int(normalized.get('x-roi-generation','-1'))!=generation:
            raise RuntimeError('Raw HTTP token/generation mismatch')
        if normalized.get('x-raw-stream')!=armed['stream_id']:raise RuntimeError('Raw HTTP stream changed')
        w,h,rgb=parse_ppm(ppm)
        magic,marker_token,marker_frame=struct.unpack('<III',rgb[:12])
        if (magic,marker_token,marker_frame)!=(MAGIC,token,fpga['frame_id']):
            raise RuntimeError('Raw marker does not identify the captured FPGA frame')
        if int(normalized.get('x-fpga-frame-id','-1'))!=marker_frame:
            raise RuntimeError('Raw marker and HTTP frame id disagree')
        report['marker']=dict(magic=hex(magic),token=marker_token,fpga_frame_id=marker_frame)
        report['stage']='read_roi_bram'
        raw=read_snapshot(probe,words)
        (output/'roi-fpga-words.bin').write_bytes(raw)
        after=probe.status();report['fpga_after_read']=after
        check_snapshot(after,token,roi,words,[w,h],marker_frame)
        actual=decode_snapshot(raw);expected=roi_from_raw(rgb,w,roi)
        (output/'roi-fpga-rgb.bin').write_bytes(actual);(output/'roi-rk-rgb.bin').write_bytes(expected)
        roi_header=('P6\n%d %d\n255\n'%(roi[2]-roi[0],roi[3]-roi[1])).encode()
        (output/'roi-fpga.ppm').write_bytes(roi_header+actual)
        (output/'roi-rk.ppm').write_bytes(roi_header+expected)
        report['comparison']=compare_rgb(actual,expected,roi)
        report['passed']=report['comparison']['passed']
        report['stage']='complete'
        if not report['passed']:report['error']='ROI RGB bytes differ'
    except Exception as exc:
        report['error']=type(exc).__name__+': '+str(exc)
    finally:
        if owns_probe:
            try:probe.write(8,CANCEL);report['fpga_cancelled']=True
            except Exception as exc:report['cleanup_errors'].append('FPGA cancel: '+str(exc))
        if generation is not None:
            try:report['camera_cancel']=api.request('/diagnostic/roi/cancel',{'generation':generation})
            except Exception as exc:report['cleanup_errors'].append('Camera cancel: '+str(exc))
        if report['cleanup_errors']:report['passed']=False
        report['elapsed_s']=time.monotonic()-started
        report['artifacts']={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                             for p in output.iterdir() if p.is_file()}
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['status','capture'],nargs='?',default='status')
    parser.add_argument('--bdf',default=None)
    parser.add_argument('--camera-url',default='http://127.0.0.1:8080')
    parser.add_argument('--scanner-url',default='http://127.0.0.1:8081')
    parser.add_argument('--roi',nargs=4,type=int,metavar=('X0','Y0','X1','Y1'),default=[256,256,288,288])
    parser.add_argument('--output',type=Path)
    parser.add_argument('--wait-seconds',type=float,default=10.0)
    args=parser.parse_args()
    if not 1<=args.wait_seconds<=20:parser.error('--wait-seconds must be between 1 and 20')
    if args.action=='capture' and args.output is None:parser.error('capture requires a NEW --output directory')
    import fcntl
    with open('/run/lock/afc03-rgb-roi-diag.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        probe=Probe(args.bdf)
        try:
            if args.action=='status':result=dict(bdf=probe.node.name,bar0=hex(probe.base),probe=probe.status())
            else:result=capture_one(probe,CameraAPI(args.camera_url),args.roi,args.output,args.wait_seconds,
                                    args.scanner_url,Path('/run/afc03-rgb-roi-last-token'))
            print(json.dumps(result,indent=2))
            return 0 if args.action=='status' or result['passed'] else 2
        finally:probe.close()


if __name__=='__main__':
    try:sys.exit(main())
    except (OSError,RuntimeError,ValueError) as exc:
        print(json.dumps({'passed':False,'error':str(exc)}),file=sys.stderr);sys.exit(2)
