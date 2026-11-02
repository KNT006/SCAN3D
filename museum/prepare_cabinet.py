"""Register completed local meshes and rasterize fallback cabinet cutouts.

Only creates display copies. Source meshes and existing exhibit geometry stay intact.
"""
from pathlib import Path
from source_inputs import required_source
import hashlib, json, shutil, sys
import numpy as np
import cv2
import trimesh

ROOT = Path(__file__).parent
PUBLIC = ROOT / 'public/museum'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def adjacency(faces):
    result = np.full((len(faces), 3), -1, np.int32)
    edges = {}
    for i, face in enumerate(faces):
        for j in range(3):
            key = tuple(sorted((int(face[j]), int(face[(j+1) % 3]))))
            if key in edges:
                a, b = edges.pop(key)
                result[i, j], result[a, b] = a, i
            else:
                edges[key] = (i, j)
    return result

def register(id, name, category, source, scan, features, processing, rotation):
    source = Path(source)
    original_hash = sha(source)
    mesh = trimesh.load(source, force='mesh', process=True)
    origin = mesh.bounds.mean(0)
    origin[1] = mesh.bounds[0, 1]
    vertices = ((mesh.vertices-origin) @ rotation).astype('<f4')
    faces = mesh.faces.astype('<u4')
    folder = PUBLIC / id
    folder.mkdir(exist_ok=True)
    vertices.tofile(folder / 'vertices.bin')
    faces.tofile(folder / 'faces.bin')
    np.zeros(len(faces), np.uint8).tofile(folder / 'face-regions.bin')
    adjacency(faces).astype('<i4').tofile(folder / 'face-adjacency.bin')
    shutil.copy2(source, folder / 'original-mm.stl')
    assert sha(source) == original_hash == sha(folder / 'original-mm.stl')
    return dict(id=id, name=name, category=category, subtitle='真实扫描，值得珍藏。',
        regions=['整体'] + [f'自定分区 {i}' for i in range(1, 8)],
        palette=['#d3a47c' if id == 'cat' else '#e9d5a4']*8,
        faces=len(faces), vertices=len(vertices), bounds_mm=np.ptp(vertices, axis=0).tolist(),
        geometry_key=hashlib.sha256(vertices.tobytes()+faces.tobytes()).hexdigest(),
        source_scan=scan, source_stl_sha256=original_hash, source_stl=f'/museum/{id}/original-mm.stl',
        features=features, processing=processing,
        segmentation_note='本展品以整体素色开始。自定分区留空，可用修正画笔建立；未进行自动语义分割。',
        transform=dict(origin=origin.tolist(), rotation=rotation.tolist()), asset_base=f'/museum/{id}/')

def cutout(item, labels=None, filename='cabinet.png'):
    folder = PUBLIC/item['id']
    v = np.fromfile(folder/'vertices.bin', '<f4').reshape(-1, 3)
    f = np.fromfile(folder/'faces.bin', '<u4').reshape(-1, 3)
    if labels is None: labels = np.fromfile(folder/'face-regions.bin', 'u1')
    az, el = .5, .24
    cam = np.array([np.cos(el)*np.sin(az), np.sin(el), np.cos(el)*np.cos(az)])
    right = np.array([np.cos(az), 0, -np.sin(az)])
    up = np.cross(cam, right)
    vv = v-(v.min(0)+v.max(0))/2
    xy = np.c_[vv@right, -vv@up]
    xy = xy*(560/max(np.ptp(xy, axis=0)))+[320, 320]
    normal = np.cross(v[f[:, 1]]-v[f[:, 0]], v[f[:, 2]]-v[f[:, 0]])
    normal /= np.maximum(np.linalg.norm(normal, axis=1)[:, None], 1e-8)
    light = np.array([-.4, .7, .6]);light /= np.linalg.norm(light)
    intensity = .68+.32*np.maximum(0, normal@light)
    colors = np.array([[int(c[k:k+2], 16) for k in [5, 3, 1]] for c in item['palette']])
    im = np.zeros((640, 640, 4), np.uint8)
    for j in np.argsort((vv@cam)[f].mean(1)):
        color = tuple((colors[labels[j]]*intensity[j]).astype(int).tolist())+(255,)
        cv2.fillConvexPoly(im, xy[f[j]].astype(np.int32), color, cv2.LINE_AA)
    cv2.imwrite(str(folder/filename), im)
    item['thumbnail'] = item['asset_base']+filename

if __name__ == '__main__':
    items = json.loads((PUBLIC/'catalog.json').read_text(encoding='utf8'))
    # Keep stable IDs/geometry keys for original entries so saved user paint survives.
    known = {i['id']:i for i in items}
    az = np.deg2rad(35)
    rotation = np.array([[np.sin(az), 0, np.cos(az)], [0, 1, 0], [-np.cos(az), 0, np.sin(az)]])
    known['cat'] = register('cat', '小猫', '小猫 · 局部重建',
        required_source('SCAN3D_CAT_STL'),
        'scan3d-20260427-214255-3f97df', ['小猫扫描的局部表面', '此旧版 STL 未保留完整外形'],
        '旧版点云重建 STL，仅保留约 21.8 mm 高的局部表面，不是完整小猫；已移除离散部分并封底。封底属于推断表面。', rotation)
    known['duck-last'] = register('duck-last', 'Duck_last', '小鸭 · 精细扫描',
        required_source('SCAN3D_DUCK_STL'),
        'scan3d-pc-20261010-163204-441887', ['圆润的身体', '扁平的嘴部', '没有脚的扫描外形'],
        '0.1125° 精细扫描的已闭合 STL，保留主体和原有曲面；平面封底属于推断表面。',
        np.array(known['duck']['transform']['rotation']))
    items = list(known.values())
    for i in items: cutout(i)
    (PUBLIC/'catalog.json').write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps([{'id':i['id'], 'faces':i['faces'], 'bounds':i['bounds_mm']} for i in items]))
