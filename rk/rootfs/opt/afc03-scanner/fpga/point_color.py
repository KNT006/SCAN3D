"""RK display-profile colour for point textures; never alter extraction RGB."""
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np


def corrected_image(rgb, bundle, led, gain=50):
    path = Path(bundle) / 'color_profile.json'
    data = path.read_bytes()
    profile = json.loads(data)
    matrix = np.asarray(profile['matrix_rgb'], dtype=np.float32)
    if (profile.get('version') != 1 or matrix.shape != (3, 4)
            or not np.isfinite(matrix).all() or np.max(np.abs(matrix)) > 4):
        raise ValueError('Invalid point colour profile')
    if profile.get('led') != led or profile.get('gain') != gain:
        raise ValueError('Point colour profile lighting/gain mismatch')
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError('Point colour requires uint8 RGB image')
    # Same encoded-RGB affine operation and uint8 clipping as RK PairPreview.
    matrix = matrix.copy()
    matrix[:, 3] *= 255
    corrected = cv2.transform(np.ascontiguousarray(rgb), matrix)
    return corrected, dict(processor='RK CPU', source='same_angle_COLOR',
        method='encoded_RGB_8bit_affine_before_bilinear_sampling',
        profile_id=profile.get('id'), profile_sha256=hashlib.sha256(data).hexdigest(),
        raw_image_preserved=True, extraction_uses_raw_RGB=True)
