"""Native-resolution 2-D ABI6 candidate processing; no geometry or hardware calls.

Reuses the project's audited software reference of the FPGA candidate extractor.
The caller owns camera acquisition, scan exclusion and serialization.
"""
import base64
import hashlib
import os
from pathlib import Path
import sys
import time

import cv2
import numpy as np

_directory = os.environ.get('DEMO_CANDIDATES_DIR')
if not _directory:
    _directory = str(Path(__file__).resolve().parents[1] / 'heterogeneous_benchmark')
sys.path.insert(0, _directory)
from candidates import load_rom_mask, candidate_uv, SETTINGS
from fast_candidates import extract_candidates, _max_channel


def decode_native(ppm):
    if not isinstance(ppm, bytes) or not ppm.startswith(b'P6'):
        raise ValueError('需要相机原始 P6 PPM，不能使用 JPEG 预览')
    image = cv2.imdecode(np.frombuffer(ppm, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.shape != (1080, 1920, 3):
        raise ValueError('需要完整 1920×1080 相机帧')
    return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)


def frame_meta(meta):
    if not isinstance(meta, dict) or not isinstance(meta.get('stream_id'), str) or not meta['stream_id']:
        raise ValueError('缺少相机流身份')
    if type(meta.get('sequence')) is not int or meta['sequence'] < 0:
        raise ValueError('缺少有效帧序号')
    return dict(meta)


def preview(image, binary=False):
    # Extraction is already complete at native resolution. Only the display is reduced.
    reduced = cv2.resize(image, (540, 960), interpolation=cv2.INTER_NEAREST if binary else cv2.INTER_AREA)
    extension = '.png' if binary else '.jpg'
    options = [] if binary else [cv2.IMWRITE_JPEG_QUALITY, 85]
    ok, data = cv2.imencode(extension, reduced, options)
    if not ok:
        raise ValueError('预览编码失败')
    return 'data:image/' + ('png' if binary else 'jpeg') + ';base64,' + base64.b64encode(data).decode('ascii')


class LiveProcessor:
    def __init__(self, rom_path, roi, selector=None):
        self.roi = tuple(map(int, roi))
        self.masks = {laser: load_rom_mask(rom_path, laser, self.roi) for laser in ('A', 'B')}
        self.rom_sha256 = hashlib.sha256(Path(rom_path).read_bytes()).hexdigest()
        self.off = self.off_rgb = self.background_meta = None
        if selector is None:
            from selector import ProductionSelector
            selector = ProductionSelector()
        self.selector = selector
        cv2.setNumThreads(1)

    def set_background(self, ppm, meta):
        metadata = frame_meta(meta)
        image = decode_native(ppm)
        self.off, self.background_meta = image, metadata
        self.off_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        return dict(background=metadata, roi=list(self.roi), rom_sha256=self.rom_sha256)

    def process(self, ppm, meta, laser, adaptive=True, stage=None):
        if stage is not None and (type(stage) is not int or not 0 <= stage < 5):
            raise ValueError('stage must be 0..4')
        started = time.perf_counter()
        metadata = frame_meta(meta)
        if laser not in self.masks:
            raise ValueError('请选择 A 或 B 激光通道')
        if self.off is None:
            raise ValueError('请先保存激光关闭时的背景帧')
        if metadata['stream_id'] != self.background_meta['stream_id']:
            raise ValueError('相机流已重启，请重新保存背景')
        if metadata['sequence'] <= self.background_meta['sequence']:
            raise ValueError('当前帧不晚于背景帧，拒绝旧帧')
        on = decode_native(ppm)
        decode_done = time.perf_counter()
        # Compute only the displayed stage. Candidate/selection inputs stay native-sized.
        records = extract_candidates(on, self.off, self.roi, self.masks[laser]) if stage is None or stage >= 3 else []
        extracted = time.perf_counter()
        selected = (self.selector.select(records, laser, self.off_rgb, adaptive=adaptive)
                    if stage is None or stage >= 3 else dict(final_uv=[], report={}, stage_counts={}))
        selected_at = time.perf_counter()
        images = {}
        if stage is None or stage in (0, 3):
            images['original'] = preview(on)
        if stage is None or stage in (1, 2):
            signal = _max_channel(cv2.subtract(on, self.off))
            if stage is None or stage == 1:
                images['difference'] = preview(signal)
            if stage is None or stage == 2:
                padded = np.pad(signal.astype(np.uint16), ((0, 0), (2, 2)), mode='reflect')
                smooth = sum(weight * padded[:, i:i+1080] for i, weight in enumerate((1, 4, 6, 4, 1)))
                images['smooth'] = preview((smooth // 16).astype(np.uint8))
        ended = time.perf_counter()
        result = dict(source='RK software ABI6 candidate reference', frame=metadata, stage=stage,
                    background=dict(self.background_meta), laser=laser,
                    roi=list(self.roi), coordinate_size=[1080, 1920], preview_size=[540, 960],
                    rom_sha256=self.rom_sha256, settings=dict(SETTINGS), signal_floor=25,
                    uv=candidate_uv(records).tolist(), count=len(records),
                    final_uv=selected['final_uv'], filter_report=selected['report'], stage_counts=selected['stage_counts'],
                    background_stale=not adaptive,
                    images=images, timings=dict(decode_ms=(decode_done-started)*1000,
                    extraction_ms=(extracted-decode_done)*1000,
                    selection_ms=(selected_at-extracted)*1000,
                    display_ms=(ended-selected_at)*1000, total_ms=(ended-started)*1000))
        if stage is None:
            result['records'] = records  # Explicit diagnostic endpoint; not sent to the display loop.
        return result
