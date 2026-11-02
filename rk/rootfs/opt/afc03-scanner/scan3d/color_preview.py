"""RK-only provisional color preview, shared latest-frame producer.

No hardware control, no camera pipeline writes, no changes to archived RGB.
Both halves of each JPEG derive from the exact same decoded source frame.
"""
import asyncio
import json
import os
import threading
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np
from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse


def validate_profile(profile):
    matrix = np.asarray(profile['matrix_rgb'], dtype=np.float32)
    if profile.get('version') != 1 or matrix.shape != (3, 4):
        raise ValueError('Invalid color profile')
    if not np.all(np.isfinite(matrix)) or np.max(np.abs(matrix)) > 4:
        raise ValueError('Unbounded color profile')
    return matrix


def make_pair(bgr, rgb_matrix):
    # cv2.transform saturates uint8; permute RGB coefficients for OpenCV BGR.
    matrix = rgb_matrix[[2, 1, 0]][:, [2, 1, 0, 3]].copy()
    matrix[:, 3] *= 255
    corrected = cv2.transform(bgr, matrix)
    return np.concatenate((bgr, corrected), axis=1)


class PairPreview:
    def __init__(self, profile_path, base):
        self.profile = json.loads(Path(profile_path).read_text(encoding='utf-8'))
        self.matrix = validate_profile(self.profile)
        self.base = base.rstrip('/')
        self.lock = threading.Lock()
        self.thread = None
        self.clients = 0
        self.last_use = 0
        self.frame = None
        self.sequence = 0
        self.updated = 0
        self.error = ''
        self.processing_ms = 0
        self.next_retry = 0

    def touch(self):
        with self.lock:
            self.last_use = time.monotonic()
            if (self.thread is None or not self.thread.is_alive()) and time.monotonic() >= self.next_retry:
                self.thread = threading.Thread(target=self.produce, daemon=True, name='rk-color-preview')
                self.thread.start()

    def produce(self):
        try:
            # Camera endpoint supplies bounded Content-Length multipart frames.
            with urllib.request.urlopen(self.base+'/stream', timeout=3) as source:
                checked = 0
                while True:
                    with self.lock:
                        if not self.clients and time.monotonic()-self.last_use > 5:
                            return
                    if time.monotonic()-checked > 1:
                        with urllib.request.urlopen(self.base+'/status',timeout=1) as reply:
                            state=json.load(reply)
                        if state.get('age',999) > 2:
                            raise ValueError('Camera frame is stale')
                        checked=time.monotonic()
                    headers = b''
                    while not headers.endswith(b'\r\n\r\n'):
                        line = source.readline(8192)
                        if not line:
                            raise ValueError('Camera stream ended')
                        headers += line
                        if len(headers) > 8192:
                            raise ValueError('Oversized camera header')
                    fields = dict(line.split(b':',1) for line in headers.split(b'\r\n') if b':' in line)
                    size = int(fields.get(b'Content-Length',b'0'))
                    if not 2 <= size <= 2*1024*1024:
                        raise ValueError('Invalid camera frame size')
                    data=source.read(size)
                    if len(data)!=size:
                        raise ValueError('Truncated camera frame')
                    started = time.monotonic()
                    bgr=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
                    if bgr is None or bgr.shape[:2] != (540,960):
                        raise ValueError('Unexpected camera preview dimensions')
                    pair=make_pair(bgr,self.matrix)
                    ok,jpeg=cv2.imencode('.jpg',pair,[cv2.IMWRITE_JPEG_QUALITY,85])
                    if not ok:
                        raise ValueError('JPEG encoding failed')
                    with self.lock:
                        self.frame=jpeg.tobytes()
                        self.sequence+=1
                        self.updated=time.monotonic()
                        self.processing_ms=(self.updated-started)*1000
                        self.error=''
        except Exception as exc:
            with self.lock:
                self.error=str(exc)
                self.frame=None
                self.next_retry=time.monotonic()+2
        finally:
            with self.lock:
                self.thread=None

    def latest(self):
        with self.lock:
            return self.sequence,self.frame if time.monotonic()-self.updated<2 else None

    async def stream(self):
        with self.lock:
            self.clients+=1
        previous=-1
        try:
            while True:
                self.touch()
                seq,data=self.latest()
                if data and seq!=previous:
                    previous=seq
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: '+str(len(data)).encode()+
                           b'\r\nX-Pair-Sequence: '+str(seq).encode()+b'\r\n\r\n'+data+b'\r\n')
                await asyncio.sleep(.025)
        finally:
            with self.lock:
                self.clients-=1
                self.last_use=time.monotonic()


def install(app, data):
    path=Path(data)/'color-calibration/profile.json'
    pair=None
    error='尚未安装颜色校正配置'
    if path.is_file():
        try:
            pair=PairPreview(path,os.environ.get('SCANNER_CAMERA_URL','http://127.0.0.1:8080'))
        except Exception as exc:
            error=str(exc)

    @app.get('/api/scan3d/color-preview/status')
    def status():
        if pair is None:
            return dict(available=False,error=error)
        with pair.lock:
            return dict(available=True,profile=pair.profile,clients=pair.clients,
                        sequence=pair.sequence,processing_ms=pair.processing_ms,error=pair.error,
                        age_seconds=time.monotonic()-pair.updated if pair.updated else None,
                        running=pair.thread is not None)

    @app.get('/api/scan3d/color-preview/pair.mjpeg')
    async def stream():
        if pair is None:
            raise HTTPException(503,error)
        return StreamingResponse(pair.stream(),media_type='multipart/x-mixed-replace; boundary=frame',
                                 headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})

    @app.get('/api/scan3d/color-preview/pair.jpg')
    async def snapshot():
        if pair is None:
            raise HTTPException(503,error)
        pair.touch()
        for _ in range(60):
            seq,image=pair.latest()
            if image:
                return Response(image,media_type='image/jpeg',headers={'Cache-Control':'no-store','X-Pair-Sequence':str(seq)})
            await asyncio.sleep(.05)
        raise HTTPException(503,'颜色预览暂不可用')
