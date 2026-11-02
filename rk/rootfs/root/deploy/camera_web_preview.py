import gi, glob, threading, time, json, uuid, struct, os
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
gi.require_version('Gst','1.0')
from gi.repository import Gst
Gst.init(None)
condition=threading.Condition()
frame=None
sequence=0
last_frame=0
capture_lock=threading.Lock()
raw_requested=False
raw_frame=None
raw_meta=None
raw_sequence=0
raw_last=0
raw_bad_sizes=0
raw_timeouts=0
raw_request_token=0
raw_pts_last=None
raw_pts_nonmonotonic=0
stream_id=uuid.uuid4().hex
from afc03_roi_capture import RoiTokenCapture, diagnostic_get, diagnostic_post
roi_capture=RoiTokenCapture(stream_id)
nodes=[p for p in glob.glob('/sys/class/video4linux/video*/name') if 'Milianke' in open(p).read()]
if len(nodes)!=1: raise RuntimeError('Camera unavailable: '+str(nodes))
device='/dev/'+nodes[0].split('/')[-2]
# Calibration illumination profile: 24 WS2812B LEDs at RGB=8; selected 2026-09-27.
import subprocess
subprocess.run(['v4l2-ctl', '-d', device, '--set-ctrl=gain=70'], check=True)
pipeline=Gst.parse_launch('v4l2src device='+device+' ! video/x-raw,format=RGB,width=1920,height=1080 ! tee name=t '
    't. ! queue max-size-buffers=2 leaky=downstream ! videorate drop-only=true ! video/x-raw,framerate=15/1 ! videoscale ! video/x-raw,width=960,height=540,pixel-aspect-ratio=1/1 ! videoconvert ! jpegenc quality=80 ! appsink name=jpeg emit-signals=true max-buffers=1 drop=true sync=false '
    't. ! queue name=raw_queue max-size-buffers=1 leaky=downstream ! appsink name=raw emit-signals=true max-buffers=1 drop=true sync=false')

# Inspect acquisition markers before any preview queue may drop a buffer.
# The instrumentation-only mode is for bounded diagnosis, never the default.
marker_capture_stage=os.environ.get('AFC03_MARKER_CAPTURE_STAGE','source')
if marker_capture_stage not in ('source','raw'):raise RuntimeError('Invalid marker capture stage')
marker_lock=threading.Lock()
marker_history=deque(maxlen=512)
marker_counts=dict(source=0,raw=0,raw_queue_overruns=0,observer_errors=0)

def marker_observe(buffer,stage):
    now=time.monotonic();size=buffer.get_size()
    pts=None if buffer.pts==Gst.CLOCK_TIME_NONE else int(buffer.pts)
    with marker_lock:
        marker_counts[stage]+=1;seq=marker_counts[stage]
    try:
        prefix=buffer.extract_dup(0,12) if size>=12 else b''
        if len(prefix)==12:
            magic,token,fpga_frame_id=struct.unpack('<III',prefix)
            if magic==0x31544752:
                with marker_lock:
                    marker_history.append(dict(stage=stage,token=token,fpga_frame_id=fpga_frame_id,
                        pts_ns=pts,monotonic_ns=int(now*1e9),sequence=seq))
        if stage==marker_capture_stage:
            roi_capture.observe_gst_buffer(buffer,dict(sequence=seq,pts_ns=pts,
                monotonic_ns=int(now*1e9),bytes=size,stream_id=stream_id,capture_stage=stage))
    except Exception:
        with marker_lock:marker_counts['observer_errors']+=1

def source_buffer(pad,info):
    b=info.get_buffer()
    if b is not None:marker_observe(b,'source')
    return Gst.PadProbeReturn.OK

def queue_overrun(queue):
    with marker_lock:marker_counts['raw_queue_overruns']+=1

def marker_diagnostics():
    with marker_lock:
        return dict(capture_stage=marker_capture_stage,stream_id=stream_id,
                    counts=dict(marker_counts),markers=list(marker_history))

pipeline.get_by_name('t').get_static_pad('sink').add_probe(Gst.PadProbeType.BUFFER,source_buffer)
pipeline.get_by_name('raw_queue').connect('overrun',queue_overrun)

def raw_sample(sink):
    global raw_requested,raw_frame,raw_meta,raw_sequence,raw_last,raw_bad_sizes
    global raw_pts_last,raw_pts_nonmonotonic
    s=sink.emit('pull-sample'); b=s.get_buffer(); now=time.monotonic()
    size=b.get_size(); pts=None if b.pts==Gst.CLOCK_TIME_NONE else int(b.pts)
    with condition:
        raw_sequence+=1; raw_last=now
        if pts is not None and raw_pts_last is not None and pts<=raw_pts_last:raw_pts_nonmonotonic+=1
        raw_pts_last=pts
        if size!=1920*1080*3:
            raw_bad_sizes+=1; return Gst.FlowReturn.OK
        # Snapshot ordinary capture state under its existing lock.
        # Diagnostics use a separate lock and copy outside this condition.
        token=raw_request_token if raw_requested else None
        meta=dict(sequence=raw_sequence,pts_ns=pts,monotonic_ns=int(now*1e9),bytes=size,stream_id=stream_id)
    marker_observe(b,'raw')
    if token is None:return Gst.FlowReturn.OK
    t=time.monotonic();data=b'P6\n1920 1080\n255\n'+b.extract_dup(0,size)
    meta['copy_ms']=(time.monotonic()-t)*1000
    with condition:
        if raw_requested and token==raw_request_token:
            raw_frame=data;raw_meta=meta;raw_requested=False;condition.notify_all()
    return Gst.FlowReturn.OK

pipeline.get_by_name('raw').connect('new-sample',raw_sample)
def sample(sink):
    global frame,sequence,last_frame
    s=sink.emit('pull-sample'); b=s.get_buffer(); data=b.extract_dup(0,b.get_size())
    with condition:
        frame=data; sequence+=1; last_frame=time.monotonic(); condition.notify_all()
    return Gst.FlowReturn.OK
pipeline.get_by_name('jpeg').connect('new-sample',sample)
from pathlib import Path
PAGE=Path(__file__).with_name('camera_alignment.html').read_text(encoding='utf-8')

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_POST(self):
        if not diagnostic_post(self,roi_capture,stream_id):self.send_error(404)
    def do_GET(self):
        global raw_requested,raw_frame,raw_meta,raw_request_token,raw_timeouts
        if diagnostic_get(self,roi_capture,stream_id):return
        path=self.path.split('?',1)[0]
        if path=='/capture.ppm':
            started=time.monotonic()
            if not capture_lock.acquire(timeout=1):
                self.send_error(503,'Another full-resolution capture is busy');return
            try:
                with condition:
                    raw_request_token+=1;raw_frame=None;raw_meta=None;raw_requested=True
                    ready=condition.wait_for(lambda:raw_frame is not None,timeout=5)
                    data=raw_frame;meta=raw_meta;raw_requested=False
                    if not ready:raw_timeouts+=1
            finally:capture_lock.release()
            if not ready:
                self.send_error(503,'No fresh full-resolution camera frame');return
            self.send_response(200);self.send_header('Content-Type','image/x-portable-pixmap')
            for k,v in {'X-Raw-Sequence':meta['sequence'],'X-Raw-PTS-Ns':meta['pts_ns'],
                        'X-Raw-Monotonic-Ns':meta['monotonic_ns'],'X-Raw-Stream':meta['stream_id'],
                        'X-Raw-Copy-Ms':meta['copy_ms'],'X-Capture-Wait-Ms':(time.monotonic()-started)*1000}.items():
                self.send_header(k,str(v))
            self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers()
            try:self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError):pass
            return
        if path=='/stream':
            self.send_response(200); self.send_header('Content-Type','multipart/x-mixed-replace; boundary=frame'); self.send_header('Cache-Control','no-store'); self.end_headers()
            previous=-1
            try:
                while True:
                    with condition:
                        condition.wait_for(lambda:sequence!=previous and frame is not None,timeout=10)
                        if frame is None or sequence==previous: continue
                        data=frame; previous=sequence
                    self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: '+str(len(data)).encode()+b'\r\n\r\n'+data+b'\r\n'); self.wfile.flush()
            except (BrokenPipeError,ConnectionResetError): pass
            return
        if path=='/diagnostic/marker-flow':
            flow=marker_diagnostics()
            from urllib.parse import urlsplit,parse_qs
            wanted=parse_qs(urlsplit(self.path).query).get('token',[None])[0]
            if wanted is not None:flow['markers']=[v for v in flow['markers'] if str(v['token'])==wanted]
            data=json.dumps(flow).encode();mime='application/json'
        elif path=='/status':
            with condition:
                info=dict(frames=sequence,age=time.monotonic()-last_frame if last_frame else 9999,
                          raw_frames=raw_sequence,raw_age=time.monotonic()-raw_last if raw_last else 9999,
                          stream_id=stream_id,raw_bad_sizes=raw_bad_sizes,raw_timeouts=raw_timeouts,
                          raw_pts_nonmonotonic=raw_pts_nonmonotonic,raw_metadata_version=1,
                          marker_capture_stage=marker_capture_stage)
            data=json.dumps(info).encode();mime='application/json'
        elif path=='/snapshot.jpg' and frame:
            data=frame; mime='image/jpeg'
        elif path=='/': data=PAGE.encode(); mime='text/html; charset=utf-8'
        else: self.send_error(404); return
        self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
pipeline.set_state(Gst.State.PLAYING)
import socket
class LocalAndLanServer(ThreadingHTTPServer):
    daemon_threads=True
    def server_bind(self):
        if self.server_address[0]!='127.0.0.1':
            self.socket.setsockopt(socket.SOL_IP,getattr(socket,'IP_FREEBIND',15),1)
        super().server_bind()
local_server=LocalAndLanServer(('127.0.0.1',8080),Handler)
lan_server=LocalAndLanServer(('192.168.1.89',8080),Handler)
threading.Thread(target=lan_server.serve_forever,daemon=True).start()
print('Serving camera '+device+' on loopback and existing direct-cable address',flush=True)
try: local_server.serve_forever()
finally:
    lan_server.shutdown();lan_server.server_close();local_server.server_close()
    pipeline.set_state(Gst.State.NULL)
