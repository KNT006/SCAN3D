"""RGB-guided recoloring groups from each exhibit's own measured cloud.

Offline preparation only: source clouds, STL and original face labels are read-only.
All thresholds are display segmentation choices, not semantic recognition.
"""
from pathlib import Path
import argparse, hashlib, json, time, warnings, html
import numpy as np
import cv2
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / 'public/museum'
PROJECT = ROOT.parent
SOURCES = {
    'duck': PROJECT/'surface-repair-20261003/duck-no-turntable/combined.npz',
    'doll': Path('F:/AAA_FPGA/scan3d-pc-archives/scan3d-pc-20261010-032157-5c3bcd/combined.npz'),
    'cat': PROJECT/'cat-ground-branch-20261008/web/combined.npz',
    'duck-last': PROJECT/'duck-last-20261010/mesh/combined.npz',
}
EXPECTED = {
    'duck': '8f9fc4c5da80b5b72afa1b315a2857c21be0ddfc3be515bbb8f36376e3e98270',
    'doll': '2d4b144c9c78a8415616b2cb197d2745b26e4e31437b2416f6653b1555dbc2dd',
    'cat': 'e9474e195e055f8b32329e351f6863374c6bc428402fcec654f851aefa726732',
    'duck-last': '524e1dc14e207661551b7cd23686203ab34fae71155225d96e781a65e1d5aca5',
}

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1<<20), b''): h.update(b)
    return h.hexdigest()

def lab(rgb):
    return cv2.cvtColor(np.asarray(rgb, np.float32).reshape(-1,1,3)/255, cv2.COLOR_RGB2LAB).reshape(-1,3)

def map_colors(item, vertices, faces):
    source = SOURCES[item['id']]
    source_hash = sha(source)
    if source_hash != EXPECTED[item['id']]: raise ValueError(f'{source}: source changed; check provenance')
    with np.load(source, allow_pickle=False) as z:
        xyz, rgb = z['xyz'], z['rgb']
        ok = np.isfinite(xyz).all(1)
        if 'inferred' in z: ok &= z['inferred'] == 0
        # Saturation here refers to RGB capture, not the saved laser-stripe flag.
        ok &= ~(rgb >= 254).any(1)
        total, kept = len(xyz), int(ok.sum())
        xyz = (xyz[ok]-np.array(item['transform']['origin']))@np.array(item['transform']['rotation'])
        rgb = rgb[ok]
    centers = vertices[faces].mean(1)
    cross = np.cross(vertices[faces[:,1]]-vertices[faces[:,0]],vertices[faces[:,2]]-vertices[faces[:,0]])
    area = np.linalg.norm(cross,axis=1)/2
    normals = cross/np.maximum(2*area[:,None],1e-12)
    distances, near = cKDTree(xyz).query(centers, k=24, workers=4)
    # Use only a small local neighbourhood; do not borrow colors across broad gaps.
    allowed = distances <= np.minimum(.9, distances[:,0]+.28)[:,None]
    samples = rgb[near].astype(np.float32)
    samples[~allowed] = np.nan
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',RuntimeWarning)
        colors = np.nanmedian(samples,axis=1)
        spread = np.nanmedian(np.linalg.norm(samples-colors[:,None,:],axis=2),axis=1)
    valid = (allowed.sum(1)>=3)&np.isfinite(colors).all(1)
    # Planar closing caps are inferred even near an edge with measured points.
    cap = (centers[:,1]<.04)&(np.abs(normals[:,1])>.97)
    valid &= ~cap
    colors[~valid] = 0
    return colors, valid, area, centers, dict(source_cloud=str(source),source_cloud_sha256=source_hash,
        source_scan=item['source_scan'],source_points=total,usable_measured_points=kept,
        query_neighbors=24,minimum_samples=3,max_distance_mm=.9,local_radius_extra_mm=.28,
        planar_cap_faces=int(cap.sum()),measured_face_fraction=float(valid.mean()),
        measured_area_fraction=float(area[valid].sum()/area.sum()),
        nearest_distance_percentiles_mm=np.percentile(distances[:,0],[50,95,99]).tolist(),
        median_sample_rgb_spread=float(np.nanmedian(spread[valid])))

def graph_components(labels, adj, selected):
    n = len(labels)
    rows = np.repeat(np.arange(n),3)
    cols = adj.ravel()
    good = cols>=0
    rows,cols=rows[good],cols[good]
    good=(labels[rows]==labels[cols])&selected[rows]&selected[cols]
    g=coo_matrix((np.ones(good.sum(),np.uint8),(rows[good],cols[good])),shape=(n,n)).tocsr()
    return connected_components(g,directed=False)[1]

def partition(colors, valid, area, adj, centers, tolerance=15., lightness=.55, photo_contrast=None):
    raw_lab=lab(colors);features=raw_lab.copy();features[:,0]*=lightness
    # Protect rare dark details before global clustering: otherwise tiny eyes
    # disappear in the objective dominated by thousands of body faces.
    ids=np.flatnonzero(valid)
    _,take=np.unique(np.floor(centers[ids]/.85).astype(int),axis=0,return_index=True)
    coarse=ids[take]
    d,ix=cKDTree(centers[coarse]).query(centers,k=min(96,len(coarse)),workers=4)
    local=raw_lab[coarse[ix],0].copy();local[(d>4.5)|(d<1.3)]=np.nan
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',RuntimeWarning)
        baseline=np.nanpercentile(local,65,axis=1)
    contrast=baseline-raw_lab[:,0]
    if photo_contrast is not None:
        contrast=np.where(np.isfinite(photo_contrast),photo_contrast,contrast)
    candidate=valid&(raw_lab[:,0]<43)&(contrast>8)&(np.linalg.norm(raw_lab[:,1:],axis=1)<19)
    seed=candidate&(((raw_lab[:,0]<39)&(contrast>10))|(contrast>15))
    if photo_contrast is not None:
        candidate &= contrast>12
        seed=candidate&((raw_lab[:,0]<37)|(contrast>22))
    comps=graph_components(np.zeros(len(colors),np.uint8),adj,candidate)
    dark=np.zeros(len(colors),bool)
    for c in np.unique(comps[seed]):
        mask=(comps==c)&candidate
        if area[mask].sum()>=.08: dark|=mask
    # Reserve a rare warm/pink accent family before area-dominated clustering.
    # This is chromatic evidence, not a hard-coded mouth/eye position.
    accent=np.zeros(len(colors),bool)
    if photo_contrast is not None:
        accent=valid&~dark&(raw_lab[:,1]>10)&(raw_lab[:,2]<20)&(raw_lab[:,0]>35)&((raw_lab[:,1]-raw_lab[:,2])>7)
        if area[accent].sum()<.04:accent[:]=False
    indices=np.flatnonzero(valid&~dark&~accent)
    if len(indices)<3: return np.full(len(colors),7,np.uint8),[]
    # Deterministic color prototypes, followed by explicit bounded merging.
    cv2.setRNGSeed(917)
    sample=features[indices].astype(np.float32)
    k=min(24,len(sample),len(np.unique(np.round(sample),axis=0)))
    _,membership,centroids=cv2.kmeans(sample,k,None,(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_MAX_ITER,100,.03),5,cv2.KMEANS_PP_CENTERS)
    membership=membership.ravel()
    groups=[dict(ids=[i],center=centroids[i],weight=float(area[indices[membership==i]].sum())) for i in range(k)]
    while len(groups)>1:
        choices=[]
        for i in range(len(groups)):
            for j in range(i):
                a,b=groups[i],groups[j]
                distance=np.linalg.norm(a['center']-b['center'])
                # A dark region can be tiny (eyes); don't merge it just for its size.
                dark_prototype=min(a['center'][0],b['center'][0])<32*lightness
                threshold=tolerance*.65 if dark_prototype else tolerance
                merged=(a['center']*a['weight']+b['center']*b['weight'])/(a['weight']+b['weight'])
                radius=max(np.linalg.norm(centroids[q]-merged) for q in a['ids']+b['ids'])
                if distance<threshold and radius<tolerance: choices.append((distance,i,j,merged))
        if not choices: break
        _,i,j,c=min(choices,key=lambda x:x[0]);a=groups.pop(i);b=groups[j]
        groups[j]=dict(ids=a['ids']+b['ids'],center=c,weight=a['weight']+b['weight'])
    # Merge by robust group representatives, including shading of the same hue.
    for g in groups:
        g['members']=indices[np.isin(membership,g['ids'])]
    while len(groups)>1:
        options=[]
        for i in range(len(groups)):
            for j in range(i):
                aa=np.median(raw_lab[groups[i]['members']],axis=0);bb=np.median(raw_lab[groups[j]['members']],axis=0)
                ca,cb=np.linalg.norm(aa[1:]),np.linalg.norm(bb[1:])
                diff=np.linalg.norm((aa-bb)*[lightness,1,1]);hue=np.dot(aa[1:],bb[1:])/max(ca*cb,1e-8)
                same_neutral=max(ca,cb)<16 and diff<tolerance
                same_hue=min(ca,cb)>15 and hue>np.cos(np.deg2rad(23)) and abs(aa[0]-bb[0])<14 and diff<23
                if same_neutral or same_hue:options.append((diff,i,j))
        if not options:break
        _,i,j=min(options);a=groups.pop(i);groups[j]['members']=np.r_[groups[j]['members'],a['members']];groups[j]['weight']+=a['weight']
    groups.sort(key=lambda g:g['weight'],reverse=True)
    labels=np.full(len(colors),255,np.uint8)
    for i,g in enumerate(groups): labels[g['members']]=i
    # Top seven color families fit the existing editor. Remaining prototypes
    # stay explicitly unknown unless genuinely close to a retained family.
    limit=7-int(dark.any())-int(accent.any())
    if len(groups)>limit:
        major=np.array([np.median(features[g['members']],axis=0) for g in groups[:limit]])
        for i,g in enumerate(groups[limit:],limit):
            d=np.linalg.norm(major-np.median(features[g['members']],axis=0),axis=1);labels[g['members']]=int(d.argmin()) if d.min()<tolerance else 255
        groups=groups[:limit]
    labels[dark]=len(groups)
    labels[accent]=len(groups)+int(dark.any())
    # Remove only small *low-contrast* islands, using bordering surface faces.
    # Unknown gaps and tiny strongly contrasting details are protected.
    labels[labels==255]=7
    components=graph_components(labels,adj,valid&(labels<7))
    for c in np.unique(components[valid&(labels<7)]):
        faces=np.flatnonzero(components==c)
        if dark[faces].any() or accent[faces].any() or len(faces)>=12 or area[faces].sum()>=.7: continue
        neighbors=np.unique(adj[faces]);neighbors=neighbors[neighbors>=0]
        neighbors=neighbors[valid[neighbors]&(labels[neighbors]!=labels[faces[0]])&(labels[neighbors]<7)]
        if not len(neighbors): continue
        target=int(np.bincount(labels[neighbors]).argmax())
        delta=np.linalg.norm(np.median(features[faces],axis=0)-np.median(features[neighbors[labels[neighbors]==target]],axis=0))
        if delta<6: labels[faces]=target
    # Stable order by surface area; no anatomical names inferred from color.
    used=sorted(np.unique(labels[labels<7]),key=lambda i:-area[labels==i].sum())
    result=np.full(len(labels),7,np.uint8);stats=[]
    for i,old in enumerate(used):
        mask=labels==old;result[mask]=i
        med=np.median(colors[mask],axis=0)
        stats.append(dict(id=i,faces=int(mask.sum()),area_mm2=float(area[mask].sum()),
            measured_rgb_median=np.round(med,1).tolist(),weighted_lab=np.median(features[mask],axis=0).tolist(),
            dark_contrast_candidate=bool(dark[mask].any()),chromatic_accent=bool(accent[mask].any())))
    return result,stats

def refine_surface(labels, colors, valid, adj, area, groups):
    """Edge-aware Potts label optimization by ICM (not a graph-cut solver).

    Rare high-contrast groups are locked. Only supported faces participate;
    unknown closure geometry cannot acquire a claimed measured label.
    """
    original=labels.copy(); features=lab(colors);features[:,0]*=.35
    known=valid&(labels<7);used=np.unique(labels[known])
    prototypes=np.array([np.median(features[labels==i],axis=0) for i in used])
    unary=np.linalg.norm(features[:,None]-prototypes[None],axis=2)**2/100
    protected=np.zeros(len(labels),bool)
    for g in groups:
        if g['dark_contrast_candidate'] or g.get('chromatic_accent'):protected|=labels==g['id']
    neighbors=np.maximum(adj,0);active=(adj>=0)&known[neighbors]&known[:,None]
    edge=np.exp(-np.sum((features[:,None]-features[neighbors])**2,axis=2)/100)*active
    # Bounded synchronous passes avoid in-place ordering bias; no global minimum claim.
    changes=[]
    for _ in range(12):
        costs=unary.copy()
        for j,label in enumerate(used):costs[:,j]+=2.2*np.sum(edge*(labels[neighbors]!=label),axis=1)
        proposed=used[costs.argmin(1)]
        update=known&~protected&(proposed!=labels)
        if not update.any():break
        labels[update]=proposed[update];changes.append(int(update.sum()))
    # Drop speckles only when the surrounding family is chromatically close.
    comps=graph_components(labels,adj,known)
    for c in np.unique(comps[known]):
        mask=(comps==c)&known
        if protected[mask].any() or area[mask].sum()>.65:continue
        nb=np.unique(adj[mask]);nb=nb[nb>=0];nb=nb[known[nb]&~mask[nb]]
        if not len(nb):continue
        target=np.bincount(labels[nb],weights=area[nb]).argmax()
        delta=np.linalg.norm(np.median(features[mask],axis=0)-np.median(features[nb[labels[nb]==target]],axis=0))
        if delta<12:labels[mask]=target
    for g in groups:
        mask=labels==g['id'];g['faces']=int(mask.sum());g['area_mm2']=float(area[mask].sum())
    return dict(method='edge-aware Potts ICM + conservative small island merge',changed_faces=int((original!=labels).sum()),iteration_changes=changes)

def render(vertices,faces,colors,path):
    im=np.full((700,1500,3),242,np.uint8)
    vv=vertices-(vertices.min(0)+vertices.max(0))/2
    for col,az in enumerate([.1,2.9]):
        el=.2;cam=np.array([np.cos(el)*np.sin(az),np.sin(el),np.cos(el)*np.cos(az)])
        right=np.array([np.cos(az),0,-np.sin(az)]);up=np.cross(cam,right)
        xy=np.c_[vv@right,-vv@up];xy*=590/max(np.ptp(xy,axis=0));xy+=[375+col*750,350]
        for j in np.argsort((vv@cam)[faces].mean(1)):
            cv2.fillConvexPoly(im,xy[faces[j]].astype(np.int32),tuple(colors[j,::-1].astype(int).tolist()),cv2.LINE_AA)
    cv2.imwrite(str(path),im)

def describe_group(g):
    if g['dark_contrast_candidate']:return '深色细节', '#343336'
    if g.get('chromatic_accent'):return '粉红细节', '#cf8b93'
    l,a,b=lab([g['measured_rgb_median']])[0];chroma=np.hypot(a,b)
    if b<-15:return ('蓝色色区','#658fae') if l>45 else ('深蓝色区','#37688a')
    if b>12:return ('橙棕色区','#de9958') if a>9 else ('黄褐色区','#b9a077')
    if a>12:return '粉紫色区','#c091a6'
    if a<-12:return '绿色色区','#819e82'
    if l<43:return '暗灰色区','#777374'
    return '浅色色区','#e9dfcf'

def write_audit(reports):
    sections=[]
    swatches=['#79c3bb','#efad5e','#718fd2','#d48091','#b4bd63','#936daa','#627076','#bbb8b1']
    for r in reports:
        rows=''.join(f'<tr><td><i style="background:{swatches[g["id"]]}"></i>{html.escape(g["name"])}</td><td>{g["faces"]:,}</td><td>{g["area_mm2"]:.1f}</td><td>{g["measured_rgb_median"]}</td></tr>' for g in r['regions'])
        sections.append(f'''<section><h2>{html.escape(r['name'])} <small>{len(r['regions'])} 个颜色组 + 未知区</small></h2>
<p>扫描：{html.escape(r['source']['source_scan'])} · 原始点数 {r['source']['source_points']:,} · 有近邻实测颜色的表面积 {r['source']['measured_area_fraction']*100:.1f}%（不是分割准确率）</p>
<div class="pair"><figure><img src="{r['id']}/rgb-segmentation/measured.jpg"><figcaption>原始 RGB 局部中位数映射 · 正反面，灰色为没有可靠颜色的表面</figcaption></figure><figure><img src="{r['id']}/rgb-segmentation/regions.jpg"><figcaption>分区示意色 · 同色代表同一上色组，不是实物颜色</figcaption></figure></div>
<table><thead><tr><th>色区（示意色）</th><th>三角面</th><th>面积 mm²</th><th>实测 RGB 中位数</th></tr></thead><tbody>{rows}<tr><td><i style="background:#bbb8b1"></i>颜色未知</td><td>{r['unknown_faces']:,}</td><td colspan="2">包括平面封底、缺少近邻颜色的推断表面</td></tr></tbody></table>
<p><a href="{r['id']}/rgb-segmentation/report.json">完整参数与来源校验报告 ↗</a> · <a href="/#exhibit/{r['id']}">进入展品上色 ↗</a></p></section>''')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SCAN3D · RGB 色区核对</title><style>body{margin:0;background:#f6f4ee;color:#35443c;font:15px/1.7 "Segoe UI","Microsoft YaHei",sans-serif}main{max-width:1500px;margin:auto;padding:40px}h1{font-weight:500}h2 small{font-size:14px;color:#758175;font-weight:400}section{background:white;border:1px solid #e1e3db;border-radius:16px;padding:24px;margin:24px 0}.pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}figure{margin:0}img{width:100%;background:#eee}figcaption{font-size:12px;color:#738070}table{border-collapse:collapse;width:100%;margin:14px 0}td,th{border-bottom:1px solid #ddd;text-align:left;padding:8px}i{display:inline-block;width:13px;height:13px;border-radius:3px;margin-right:8px}a{color:#476d60}p{color:#637464}.method{background:#e8ede4;border-radius:12px;padding:20px}@media(max-width:900px){main{padding:16px}.pair{grid-template-columns:1fr}table{font-size:12px}}</style><main><a href="/">← 陈列柜</a><h1>用实测颜色划分上色区域</h1><div class="method">每件网格只读取其对应扫描的点云；沿用已有毫米坐标变换，没有再次配准。每个三角面中心取附近实测 RGB 的中位数，距离上限 0.9 mm，至少 3 点；补洞点和 RGB 饱和点不作为颜色证据。<br>RGB 转 Lab，亮度差权重 0.55；颜色聚类后合并相近色与同色相的明暗变化，再沿表面邻接清理低对比碎块。小而高对比的深色细节单独保护。相同色区可以跨越不同身体部位。<br>这是颜色分组，不是五官语义识别。阴影、原始颜色错位和低分辨率会影响边界；深色组也可能包含阴影。未知区不被假称为实测颜色。可在展品页面用画笔修正，或切回原有手动分区。</div>'''+''.join(sections)+'</main></html>'
    (PUBLIC/'rgb-segmentation.html').write_text(page,encoding='utf8')

def run(publish=False,tolerance=15.,lightness=.55,photos=False):
    catalog=json.loads((PUBLIC/'catalog.json').read_text(encoding='utf8'));reports=[]
    for item in catalog:
        start=time.perf_counter();folder=PUBLIC/item['id'];out=folder/'rgb-segmentation';out.mkdir(exist_ok=True)
        v=np.fromfile(folder/'vertices.bin','<f4').reshape(-1,3);f=np.fromfile(folder/'faces.bin','<u4').reshape(-1,3)
        adj=np.fromfile(folder/'face-adjacency.bin','<i4').reshape(-1,3)
        key=hashlib.sha256(v.tobytes()+f.tobytes()).hexdigest();assert key==item['geometry_key']
        cache=ROOT/'assets'/f'{item["id"]}-measured-face-colors.npz'
        if cache.exists():
            z=np.load(cache);colors,valid,area,centers=z['colors'],z['valid'],z['area'],z['centers'];mapping=json.loads(str(z['mapping']))
            assert str(z['geometry_key'])==key and mapping['source_cloud_sha256']==EXPECTED[item['id']]==sha(SOURCES[item['id']])
        else:
            colors,valid,area,centers,mapping=map_colors(item,v,f)
            np.savez_compressed(cache,colors=colors,valid=valid,area=area,centers=centers,mapping=json.dumps(mapping),geometry_key=key)
        photo=None;refinement=None
        if photos:
            from image_colors import photo_evidence
            photo=photo_evidence(item,v,f,out)
            if photo is not None:
                # Flat inferred caps stay unknown even if a camera glimpses them.
                cross=np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]])
                cap=(centers[:,1]<.04)&(np.abs(cross[:,1])/np.maximum(np.linalg.norm(cross,axis=1),1e-8)>.97)
                measured=photo['valid']&~cap
                colors=colors.copy();colors[measured]=photo['colors'][measured]
                valid=valid|measured
                pc=np.zeros(len(f));pc[measured]=photo['contrast'][measured]
                mapping={**mapping,'photo_evidence':json.loads(str(photo['metadata'])),'photo_supported_faces':int(measured.sum()),'photo_supported_area_fraction':float(area[measured].sum()/area.sum()),'color_evidence_area_fraction':float(area[valid].sum()/area.sum())}
        labels,groups=partition(colors,valid,area,adj,centers,tolerance,lightness,pc if photo is not None else None)
        if photo is not None:refinement=refine_surface(labels,colors,valid,adj,area,groups)
        names=[];pal=[]
        for g in groups:
            name,color=describe_group(g);name=f'{name} {g["id"]+1}';names.append(name);pal.append(color);g['name']=name
        names+=[f'自定分区 {i+1}' for i in range(len(groups),7)]+['颜色未知']
        # Uniform, editable display colors: segmentation uses RGB; display need not reproduce noisy capture colors.
        pal+=['#d6d4cc']*(7-len(pal))+['#d5d2cb']
        debug=np.array([[int(c[j:j+2],16) for j in (1,3,5)] for c in ['#79c3bb','#efad5e','#718fd2','#d48091','#b4bd63','#936daa','#627076','#bbb8b1']])
        labels.tofile(out/'face-regions.bin')
        render(v,f,debug[labels],out/'regions.jpg')
        measured=colors.copy();measured[~valid]=[210,210,210]
        render(v,f,measured,out/'measured.jpg')
        report=dict(id=item['id'],name=item['name'],algorithm=('visibility-aware calibrated photos + SLIC + weighted view fusion + Lab groups + edge-aware ICM' if photo is not None else 'weighted-Lab prototypes + bounded color merging + surface island cleanup'),photo_refinement=refinement,
            semantic_recognition=False,geometry_key=key,source=mapping,settings=dict(color_tolerance=tolerance,lightness_weight=lightness,
            max_color_groups=7,unknown_label=7,low_contrast_island_delta=6,
            neutral_chroma_max=16,same_hue_max_degrees=23,same_hue_max_lightness_delta=14,same_hue_max_distance=23,
            dark_local_radius_mm=[1.3,4.5],dark_baseline_percentile=65,dark_max_L=43,dark_min_contrast=8,
            dark_seed_L=39,dark_seed_contrast=10,dark_strong_contrast=15,dark_min_area_mm2=.08),regions=groups,
            unknown_faces=int((labels==7).sum()),unknown_area_fraction=float(area[labels==7].sum()/area.sum()),
            elapsed_seconds=round(time.perf_counter()-start,3),original_geometry_unchanged=True)
        if photo is not None:
            report['settings'].update(dark_min_contrast=12,dark_seed_L=37,dark_strong_contrast=22,
                dark_seed_rule='L < 37 OR contrast > 22, after contrast > 12 and L < 43',
                accent_rule='a > 10, b < 20, L > 35, a-b > 7; measured RGB only',
                unsupported_photo_dark_candidates=False,mesh_optimizer='ICM, 12 bounded passes; not graph cuts',
                label_texture_generated=False)
        report_path=out/'report.json';report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        seg_hash=sha(out/'face-regions.bin')[:16]
        item['color_segmentation']=dict(version=('photo-v2-' if photo is not None else 'rgb-lab-v1-')+seg_hash,regions=names,palette=pal,
            labels_file=f'rgb-segmentation/face-regions.bin?v={seg_hash}',
            note=('融合本次扫描多角度 RGB 原图与对应点云，检查可见性后保留细节、合并相近颜色。灰色为颜色未知；不是五官语义识别。' if photo is not None else '依据本展品实测点云 RGB 色差合并；同色可跨部位共用上色。灰色未知区缺少可靠实测颜色，非语义识别。'),
            report_url=item['asset_base']+'rgb-segmentation/report.json',thumbnail=item['asset_base']+'rgb-segmentation/cabinet.png',region_count=len(groups),
            measured_area_fraction=mapping['measured_area_fraction'],unknown_faces=report['unknown_faces'])
        from prepare_cabinet import cutout
        cutout({**item,'palette':pal},labels,'rgb-segmentation/cabinet.png')
        assert hashlib.sha256((folder/'vertices.bin').read_bytes()+(folder/'faces.bin').read_bytes()).hexdigest()==key
        reports.append(report)
        print(json.dumps(dict(id=item['id'],mapped=mapping['measured_area_fraction'],unknown=report['unknown_area_fraction'],groups=groups),ensure_ascii=False),flush=True)
    (ROOT/'assets/rgb-segmentation-report.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf8')
    write_audit(reports)
    if photos:
        previous=json.loads((PUBLIC/'rgb-v1/catalog.json').read_text(encoding='utf8'))
        for item in catalog:
            old=next(x for x in previous if x['id']==item['id'])['color_segmentation'].copy()
            old['labels_file']=f'../rgb-v1/{item["id"]}/face-regions.bin'
            old['thumbnail']=f'/museum/rgb-v1/{item["id"]}/cabinet.png'
            old['report_url']=f'/museum/rgb-v1/{item["id"]}/report.json'
            item['previous_color_segmentation']=old
    if publish: (PUBLIC/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf8')
    if photos and publish:
        from photo_audit import write_photo_audit
        write_photo_audit(reports)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--publish',action='store_true');p.add_argument('--photos',action='store_true');p.add_argument('--tolerance',type=float,default=15);p.add_argument('--lightness',type=float,default=.55)
    args=p.parse_args();run(args.publish,args.tolerance,args.lightness,args.photos)
