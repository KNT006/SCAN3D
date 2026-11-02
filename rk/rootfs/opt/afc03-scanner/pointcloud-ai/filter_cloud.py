"""Review-only AI silhouette filtering. Never changes scan inputs or fills holes."""
import argparse
import hashlib
import json
import math
import struct
import time
from pathlib import Path

import cv2
import numpy as np


def preprocess(bgr):
    image = cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), (320, 320)).astype(np.float32)
    image /= max(float(image.max()), 1.0)
    return (image - np.array([.485, .456, .406], np.float32)) / np.array([.229, .224, .225], np.float32)


def load_cloud(path):
    if path.suffix == '.npz':
        with np.load(path, allow_pickle=False) as data:
            fields = {k: data[k] for k in data.files}
        xyz, rgb = fields['xyz'], fields['rgb']
    else:
        raw = path.read_bytes()
        magic, version, count, total = struct.unpack('<4I', raw[:16])
        if magic != 0x31443353 or version != 1 or count != total or len(raw) != 16 + count*15:
            raise ValueError('Unsupported or incomplete cloud binary')
        xyz = np.frombuffer(raw, '<f4', count*3, 16).reshape(-1, 3)
        rgb = np.frombuffer(raw, 'u1', count*3, 16+count*12).reshape(-1, 3)
        fields = dict(xyz=xyz, rgb=rgb)
    if xyz.ndim != 2 or xyz.shape[1] != 3 or rgb.shape != xyz.shape or not np.isfinite(xyz).all():
        raise ValueError('Invalid cloud coordinates/colors')
    return fields


def select_points(outside, observed, view_count, ratio):
    # At least four independent valid views must contradict a point.
    return (outside >= max(4, math.ceil(view_count*ratio))) & (observed >= 4)


def project_pixels(camera, matrix, distortion):
    """OpenCV's five-coefficient projection, without unused Jacobian allocation.

    Other distortion models use OpenCV unchanged. Arithmetic stays float64;
    no point sampling, model quantization, or silhouette simplification.
    """
    coefficients = np.asarray(distortion, dtype=np.float64).reshape(-1)
    matrix = np.asarray(matrix, dtype=np.float64)
    if len(coefficients) != 5:
        return cv2.projectPoints(camera, np.zeros(3), np.zeros(3), matrix, coefficients)[0][:, 0]
    k1, k2, p1, p2, k3 = coefficients
    z = camera[:, 2]
    inverse = np.ones_like(z)
    np.divide(1.0, z, out=inverse, where=z != 0)
    x = camera[:, 0]*inverse
    y = camera[:, 1]*inverse
    xx, yy, xy = x*x, y*y, x*y
    radius = xx+yy
    radial = 1+k1*radius+k2*radius*radius+k3*radius*radius*radius
    u = matrix[0, 0]*(x*radial+2*p1*xy+p2*(radius+2*xx))+matrix[0, 2]
    v = matrix[1, 1]*(y*radial+p1*(radius+2*yy)+2*p2*xy)+matrix[1, 2]
    return np.column_stack((u, v))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cloud', type=Path, required=True)
    ap.add_argument('--manifest', type=Path, required=True, help='Explicit calibrated views, ROI, rotations and angles')
    ap.add_argument('--model', type=Path, required=True)
    ap.add_argument('--backend', choices=['onnx', 'rknn'], required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--margin', type=int, default=14, help='Full resolution pixel dilation')
    ap.add_argument('--outside-ratio', type=float, default=.13)
    args = ap.parse_args()
    if not 0 < args.outside_ratio <= 1 or not 0 <= args.margin <= 100:
        ap.error('Invalid filtering thresholds')
    spec = json.loads(args.manifest.read_text(encoding='utf-8'))
    if spec.get('coordinate_frame') != 'axis_frame_mm' or len(spec['views']) < 4:
        raise ValueError('Requires calibrated axis-frame points and at least four saved RGB views')
    angles = [round(float(view['angle_degrees']) % 360, 5) for view in spec['views']]
    if len(angles) > 65535 or len(set(angles)) != len(angles) or not np.isfinite(angles).all():
        raise ValueError('Views must have unique, finite angles; omit duplicate closure frame')
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'manifest.json').write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding='utf-8')
    cv2.setNumThreads(2)
    if args.backend == 'onnx':
        import onnxruntime as ort
        options = ort.SessionOptions(); options.intra_op_num_threads = 2
        runtime = ort.InferenceSession(str(args.model), options, providers=['CPUExecutionProvider'])
        infer = lambda image: runtime.run(None, {runtime.get_inputs()[0].name: image.transpose(2, 0, 1)[None]})[0]
    else:
        from rknnlite.api import RKNNLite
        runtime = RKNNLite()
        if runtime.load_rknn(str(args.model)) != 0 or runtime.init_runtime(core_mask=RKNNLite.NPU_CORE_0) != 0:
            raise RuntimeError('NPU initialization failed; no silent CPU fallback')
        infer = lambda image: runtime.inference(inputs=[image[None]], data_format=['nhwc'])[0]
    start_time = time.monotonic()
    fields = load_cloud(args.cloud); xyz = fields['xyz']; count = len(xyz)
    axis = spec['axis']; cam = spec['camera']
    direction = np.array(axis['axis_direction_for_positive_pulses_camera'], float)
    direction /= np.linalg.norm(direction)
    center = np.array(axis['axis_point_closest_to_camera_origin_mm'])
    ex = np.array([1., 0, 0]); ex -= direction*(ex@direction); ex /= np.linalg.norm(ex)
    basis = np.array([ex, direction, np.cross(ex, direction)])
    outside = np.zeros(count, np.uint16); observed = np.zeros(count, np.uint16)
    stats = []
    for view in spec['views']:
        path = args.manifest.parent / view['path']
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError(f'Missing RGB image: {path}')
        rotation = view['rotate_clockwise_degrees']
        if rotation not in (0, 90, 180, 270):
            raise ValueError('Unsupported image rotation')
        image = np.rot90(image, -(rotation//90)).copy()
        height, width = image.shape[:2]
        x0, y0, x1, y1 = spec['roi']
        if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
            raise ValueError('ROI outside saved image')
        tick = time.monotonic()
        pred = np.asarray(infer(preprocess(image[y0:y1, x0:x1]))).squeeze()
        latency = time.monotonic()-tick
        if pred.shape != (320, 320) or not np.isfinite(pred).all():
            raise ValueError('Invalid segmentation output')
        span = float(pred.max()-pred.min())
        if span < .01:
            raise ValueError('Flat segmentation; manual review required')
        pred = (pred-pred.min())/span
        fg = (cv2.resize(pred, (x1-x0, y1-y0)) >= .5).astype(np.uint8)
        area = float(fg.mean())
        if not .03 < area < .90:
            raise ValueError('Implausible foreground area; manual review required')
        # Out-of-ROI pixels are unknown, never evidence of background.
        mask = np.zeros((height, width), np.uint8); mask[y0:y1, x0:x1] = fg
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*args.margin+1,)*2)
        expanded = cv2.dilate(mask, kernel)
        rot = cv2.Rodrigues(direction*np.deg2rad(view['angle_degrees']))[0]
        for lo in range(0, count, 100000):
            hi = min(lo+100000, count)
            camera = (xyz[lo:hi]@basis)@rot.T+center
            uv = project_pixels(camera, cam['camera_matrix'], cam['distortion_coefficients'])
            uv = np.rint(uv).astype(np.int64)
            valid = (camera[:, 2] > 0)&(uv[:, 0] >= x0)&(uv[:, 0] < x1)&(uv[:, 1] >= y0)&(uv[:, 1] < y1)
            bad = np.zeros(hi-lo, bool); bad[valid] = expanded[uv[valid, 1], uv[valid, 0]] == 0
            outside[lo:hi] += bad; observed[lo:hi] += valid
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(image, contours, -1, (0, 255, 0), 2)
        cv2.imwrite(str(args.output/f"view-{view['frame']:04d}.jpg"), image[y0:y1, x0:x1])
        stats.append(dict(frame=view['frame'], foreground_fraction=area, inference_seconds=latency,
                          image_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        print(json.dumps(stats[-1]), flush=True)
    rejected = select_points(outside, observed, len(stats), args.outside_ratio)
    report = dict(method='U2NETP foreground + calibrated multiview rejection', backend=args.backend,
                  source_sha256=hashlib.sha256(args.cloud.read_bytes()).hexdigest(),
                  model_sha256=hashlib.sha256(args.model.read_bytes()).hexdigest(),
                  input_points=count, rejected_points=int(rejected.sum()), retained_points=int((~rejected).sum()),
                  added_points=0, accuracy_validated=False, activated=False, views=stats,
                  margin_pixels=args.margin, outside_ratio=args.outside_ratio, elapsed_seconds=time.monotonic()-start_time)
    report['review_required'] = True
    report['output_accepted'] = float(rejected.mean()) <= .1
    (args.output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    np.savez_compressed(args.output/'votes.npz', outside=outside, observed=observed, keep=~rejected)
    if not report['output_accepted']:
        raise RuntimeError('More than 10% rejected; saved votes only, no replacement cloud')
    for name, selection in [('combined', ~rejected), ('rejected', rejected)]:
        output = {k: v[selection] if v.ndim > 0 and len(v) == count else v for k, v in fields.items()}
        if 'source_index' not in output:
            output['source_index'] = np.flatnonzero(selection)
        if 'inferred' not in output:
            output['inferred'] = np.zeros(int(selection.sum()), np.uint8)
        np.savez_compressed(args.output/(name+'.npz'), **output)
    if args.backend == 'rknn':
        runtime.release()
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
