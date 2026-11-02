"""Saved-mesh cleanup and boundary-only base closure; all coordinates in mm."""
import numpy as np
import trimesh
from scipy.spatial import cKDTree
from shapely.geometry import Polygon

VERSION = 'rk-boundary-cap-v1'

def edge_counts(mesh):
    return np.bincount(mesh.edges_unique_inverse, minlength=len(mesh.edges_unique))

def boundary_polygons(edges, xy):
    """Degree-two loops and nesting without the optional native R-tree package."""
    adjacency = {}
    for a, b in edges:
        adjacency.setdefault(int(a), []).append(int(b))
        adjacency.setdefault(int(b), []).append(int(a))
    unseen = set(adjacency); loops = []
    while unseen:
        seed = min(unseen); current = seed; previous = None; loop = []
        while True:
            if current not in unseen:
                if current != seed:raise ValueError('底部边界环异常')
                break
            unseen.remove(current);loop.append(current)
            following = next(v for v in adjacency[current] if v != previous)
            previous, current = current, following
        polygon = Polygon(xy[loop])
        if not polygon.is_valid or polygon.area <= 0:raise ValueError('底部轮廓无效')
        loops.append(polygon)
    parents = []
    for i, p in enumerate(loops):
        containers = []
        for j, q in enumerate(loops):
            if j == i:continue
            if p.boundary.intersects(q.boundary):raise ValueError('底部轮廓相交')
            if q.contains(p):containers.append(j)
        parents.append(min(containers,key=lambda j:loops[j].area) if containers else None)
    depth = []
    for i in range(len(loops)):
        d=0;j=parents[i]
        while j is not None:d+=1;j=parents[j]
        depth.append(d)
    return [Polygon(p.exterior.coords,[q.exterior.coords for j,q in enumerate(loops) if parents[j]==i])
            for i,p in enumerate(loops) if depth[i]%2==0]

def cap_boundary(mesh, height):
    mesh.merge_vertices()
    counts = edge_counts(mesh)
    if (counts > 2).any():
        raise ValueError('封底前存在非流形边；未强行封口，请调整重建参数')
    edges = mesh.edges_unique[counts == 1]
    if not len(edges):
        return mesh, 0
    # Only calibrated plane edges can be capped. Other holes require review.
    tolerance = max(1e-5, float(np.max(mesh.extents)) * 1e-7)
    on_plane = np.all(np.abs(mesh.vertices[edges, 1] - height) <= tolerance, axis=1)
    base = edges[on_plane]
    if not len(base):
        raise ValueError('存在非底面缺口，无法通过转盘平面封闭')
    ids, degree = np.unique(base, return_counts=True)
    if not np.all(degree == 2):
        raise ValueError('底部边界不是闭合环，保留原始网格供复核')
    polygons = boundary_polygons(base, mesh.vertices[:, [0, 2]])
    if not polygons:
        raise ValueError('无法构造底部轮廓')
    tree = cKDTree(mesh.vertices[ids][:, [0, 2]])
    faces = []
    for polygon in polygons:
        if not polygon.is_valid or polygon.area <= 0:
            raise ValueError('底部轮廓相交或退化，未生成封底')
        vertices, triangles = trimesh.creation.triangulate_polygon(polygon, engine='earcut')
        distance, nearest = tree.query(vertices)
        if np.max(distance) > tolerance:
            raise ValueError('封底三角化引入了非边界顶点')
        faces.append(ids[nearest][triangles])
    original_vertices = mesh.vertices.copy()
    original_bounds = mesh.bounds.copy()
    added = np.vstack(faces)
    # Earcut may omit collinear contour vertices. Reinsert them by splitting
    # the corresponding cap triangle edge, so the surface has no T-junctions.
    cap_edges = np.sort(np.vstack([added[:, [0, 1]], added[:, [1, 2]], added[:, [2, 0]]]), axis=1)
    unique, counts_cap = np.unique(cap_edges, axis=0, return_counts=True)
    original_edges = {tuple(sorted(e)) for e in base}
    triangles = added.tolist()
    xy = mesh.vertices[:, [0, 2]]
    for a, b in unique[counts_cap == 1]:
        if (int(a), int(b)) in original_edges:
            continue
        delta = xy[b] - xy[a]; length = float(np.linalg.norm(delta))
        candidates = ids[tree.query_ball_point((xy[a] + xy[b]) / 2, length / 2 + tolerance)]
        t = (xy[candidates] - xy[a]) @ delta / (length * length)
        distance = np.linalg.norm(xy[candidates] - (xy[a] + t[:, None] * delta), axis=1)
        middle = candidates[(t > 1e-9) & (t < 1 - 1e-9) & (distance < tolerance)]
        if not len(middle):
            raise ValueError('封底边界与原始轮廓不一致')
        middle = middle[np.argsort((xy[middle] - xy[a]) @ delta)]
        row = next(i for i, f in enumerate(triangles) if a in f and b in f)
        f = triangles[row]; opposite = next(v for v in f if v != a and v != b)
        chain = [int(a), *map(int, middle), int(b)]
        pieces = [[chain[i], chain[i+1], opposite] for i in range(len(chain)-1)]
        triangles[row] = pieces[0]; triangles.extend(pieces[1:])
    added = np.asarray(triangles, dtype=np.int64)
    mesh.faces = np.vstack((mesh.faces, added))
    mesh.face_attributes.clear()
    mesh.fix_normals()
    if not np.array_equal(original_vertices, mesh.vertices) or not np.array_equal(original_bounds, mesh.bounds):
        raise ValueError('封底意外改变主体坐标')
    return mesh, len(added)

def finish_mesh(mesh, out, cut, cap, holes, cleanup, check=lambda: None):
    if cleanup not in ('main', 'small', 'none'):
        raise ValueError('无效碎片清理模式')
    mesh.export(out / 'unrepaired-mm.stl')
    before_bounds = mesh.bounds.copy()
    if cut is not None:
        mesh = mesh.slice_plane(plane_origin=[0, cut, 0], plane_normal=[0, 1, 0], cap=False)
    if not len(mesh.faces):
        raise ValueError('裁剪后无有效网格，请检查转盘高度')
    mesh.merge_vertices()
    mesh.remove_unreferenced_vertices()
    parts = sorted(mesh.split(only_watertight=False, repair=False), key=lambda p: p.area, reverse=True)
    kept = parts[:1] if cleanup == 'main' else ([p for p in parts if p.area >= parts[0].area * .002] if cleanup == 'small' else parts)
    removed = parts[len(kept):]
    if removed:
        trimesh.util.concatenate(removed).export(out / 'removed-fragments.stl')
    mesh = trimesh.util.concatenate(kept)
    check()
    # Fill only tiny side holes first. Planar base closure uses the full contour,
    # including nested contours/holes, rather than a triangle fan or convex hull.
    n = len(mesh.faces)
    if holes:
        trimesh.repair.fill_holes(mesh)
    small_added = len(mesh.faces) - n
    mesh.fix_normals()
    pre_cap_bounds = mesh.bounds.copy()
    added = 0
    if cap:
        if cut is None or not np.isfinite(cut):
            raise ValueError('缺少有效转盘高度，不能自动封底')
        mesh, added = cap_boundary(mesh, cut)
    mesh.fix_normals()
    if mesh.volume < 0:
        mesh.invert()
    check()
    if cap and (not mesh.is_watertight or not mesh.is_winding_consistent):
        mesh.export(out / 'repair-review-mm.stl')
        raise ValueError('封底后仍有非底面缺口或绕向异常；保留中间文件，未标为闭合完成')
    return mesh, dict(postprocess_version=VERSION, cleanup_mode=cleanup,
        components_before=len(parts), connected_components=len(kept), components_removed=len(removed),
        cleanup_removed_triangles=sum(len(p.faces) for p in removed),
        component_areas_mm2=[float(p.area) for p in parts], original_stl_preserved=True,
        unrepaired_stl='unrepaired-mm.stl', removed_fragments_file='removed-fragments.stl' if removed else None,
        small_hole_added_triangles=small_added, added_base_triangles=added,
        base_capped=bool(cap), base_is_estimated=bool(added), base_plane_y_mm=cut if cap else None,
        pre_cleanup_bounds_mm=before_bounds.tolist(), pre_cap_bounds_mm=pre_cap_bounds.tolist(),
        cap_coordinates_unchanged=bool(np.array_equal(mesh.bounds, pre_cap_bounds)))
