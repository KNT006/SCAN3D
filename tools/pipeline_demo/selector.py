"""Production RK stripe selection with angle-invariant geometry for a 2-D preview.

No motion evidence is invented: this adapter never calls the scan alignment path.
Camera-ray intersections are temporary and used only for height/radius rejection.
"""
import json
import os
from pathlib import Path
import sys
import numpy as np

_fpga = Path(os.environ.get('DEMO_FPGA_DIR', '/opt/afc03-scanner/fpga'))
if not _fpga.exists():
    _fpga = Path(__file__).resolve().parents[2] / 'rk/rootfs/opt/afc03-scanner/fpga'
sys.path.insert(0, str(_fpga))
from pointcloud_adapter import PointCloudAdapter
from dual_identity import geometry_candidates
from rk_candidate_policy import select_candidates, VERSION
from rgb_adaptive_strategy import color_thresholds, HASHES
from turntable_filter import load_filter, filter_mask
from spatial_filter import validate


class PreviewGeometryAdapter(PointCloudAdapter):
    """Unaligned camera-to-axis geometry; safe to evaluate while an object moves.

Rotation about the calibrated axis changes neither height nor radial distance.
This result must never be used to assemble a multi-angle cloud.
"""
    def reconstruct(self, frame):
        label = frame.header['laser_id']
        uv = np.asarray(frame.processing_uv(), float).reshape(-1, 2)
        if label not in ('A', 'B'):
            raise ValueError('single laser identity required')
        direction = np.asarray(self.axis['axis_direction_for_positive_pulses_camera'], float)
        direction = direction / np.linalg.norm(direction)
        center = np.asarray(self.axis['axis_point_closest_to_camera_origin_mm'], float)
        if len(uv):
            labels, clouds = self.geometry_candidates(uv, self.camera, self.planes, self.axis,
                                                       max_radius_mm=None)
            keep = np.array([label in candidate for candidate in labels], bool)
            xyz = clouds[label][keep]
        else:
            keep = np.zeros(0, bool)
            xyz = np.empty((0, 3))
        ex = np.array([1., 0., 0.]); ex -= direction * (ex @ direction)
        ex /= np.linalg.norm(ex)
        ez = np.cross(ex, direction)
        delta = xyz - center
        axis = np.c_[delta @ ex, delta @ direction, delta @ ez]
        accepted, _ = filter_mask(axis, self.turntable_filter)
        ids = np.flatnonzero(keep)[accepted]
        return dict(uv=uv[ids], camera_xyz_mm=xyz[accepted],
                    camera_aligned_mm=xyz[accepted], axis_frame_mm=axis[accepted],
                    kept_record_indices=ids)


class ProductionSelector:
    def __init__(self, bundle=None, spatial_profile=None):
        bundle = Path(bundle) if bundle is not None else _fpga / 'new-strategy-bundle'
        spatial_profile = Path(spatial_profile) if spatial_profile is not None else Path(
            '/userdata/afc03-scanner/jobs/scan3d-work/spatial-profile.json')
        self.adapter = PreviewGeometryAdapter(bundle, geometry_candidates)
        if self.adapter.hashes != HASHES:
            raise ValueError('实时筛选标定与部署策略不一致')
        self.adapter.turntable_filter = load_filter(bundle, self.adapter.hashes)
        if self.adapter.turntable_filter is None:
            raise ValueError('缺少已启用的转盘高度筛选配置')
        self.adapter.spatial_filter = validate(json.loads(spatial_profile.read_text(encoding='utf-8')))
        cfg = self.adapter.spatial_filter
        if (not cfg['enabled'] or cfg['radius_mm'] != 70 or cfg['margin_mm'] != 0 or
            cfg.get('axis_sha256', self.adapter.hashes['axis_sha256']) != self.adapter.hashes['axis_sha256']):
            raise ValueError('实时空间配置与 ABI6 半径/标定不匹配')

    def select(self, records, laser, off_rgb, adaptive=True):
        if laser not in ('A', 'B'):
            raise ValueError('请选择单一激光通道')
        raw = []
        for y, num, den, tag, lo, hi, k, strength in records:
            if den <= 0:
                raise ValueError('无效候选质心分母')
            raw.append(dict(x=num/den, y=y, k=k, peak32=strength, lo=lo, hi=hi,
                            width=hi-lo+1, signalmax=tag & 255, saturated=(tag >> 8) & 1))
        if adaptive:
            if not isinstance(off_rgb, np.ndarray) or off_rgb.dtype != np.uint8 or off_rgb.shape != (1920, 1080, 3):
                raise ValueError('需要旋转后的完整 RGB 背景图')
            for r, color in zip(raw, color_thresholds(off_rgb, raw)):
                r.update(color)
        else:
            # Both branches are constrained to >=40: no stale-color weak additions.
            for r in raw:
                r.update(rgb=[0., 0., 0.], v=0., color_spread=0., color_reliable=False,
                         color_threshold=40, threshold=40)
        trace = {}
        arrays, report, _ = select_candidates(raw, {'laser_id': laser}, self.adapter,
                                             diagnostics=False, trace=trace)
        report.update(selection_version=VERSION,
                      color_source='saved_OFF_RGB_not_standard_COLOR' if adaptive else 'fixed40_stale_background',
                      adaptive_enabled=bool(adaptive),
                      geometry_scope='camera_to_axis_height_radius_only_no_angular_alignment',
                      pointcloud_saved=False, long_track_diagnostics=False)
        return dict(final_uv=arrays['uv'].tolist(), report=report,
                    stage_counts={key:len(trace[key]) for key in
                                  ('finite', 'ground', 'geometry', 'merged', 'after_secondary', 'final')})
