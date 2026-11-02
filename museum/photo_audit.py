"""Comparison page for actual measured photo evidence and editable flat regions."""
import json,html
import numpy as np
from segment_colors import PUBLIC,render

def write_photo_audit(reports):
    old=json.loads((PUBLIC/'rgb-v1/catalog.json').read_text(encoding='utf8'))
    old={x['id']:x for x in old}
    catalog=json.loads((PUBLIC/'catalog.json').read_text(encoding='utf8'))
    catalog={x['id']:x for x in catalog}
    sections=[]
    for r in reports:
        ident=r['id'];folder=PUBLIC/ident;out=folder/'rgb-segmentation'
        v=np.fromfile(folder/'vertices.bin','<f4').reshape(-1,3);f=np.fromfile(folder/'faces.bin','<u4').reshape(-1,3)
        def palette(p):return np.array([[int(c[j:j+2],16) for j in [1,3,5]] for c in p])
        newlabels=np.fromfile(out/'face-regions.bin',np.uint8)
        oldlabels=np.fromfile(PUBLIC/'rgb-v1'/ident/'face-regions.bin',np.uint8)
        render(v,f,palette(old[ident]['color_segmentation']['palette'])[oldlabels],out/'before-filled.jpg')
        render(v,f,palette(catalog[ident]['color_segmentation']['palette'])[newlabels],out/'after-filled.jpg')
        source=r['source'];photo=source.get('photo_evidence')
        evidence='本展品暂缺可用多视角照片，保留点云分区。'
        if photo:
            evidence=f"使用 {len(photo['views'])} 个视角；照片支持表面积 {source['photo_supported_area_fraction']*100:.1f}%。坐标重投影核对已通过（只证明归档坐标链一致，不代表实物扫描精度）。"
        figures=''.join(f'<figure><img loading="lazy" src="{ident}/rgb-segmentation/{file}"><figcaption>{caption}</figcaption></figure>' for file,caption in [('before-filled.jpg','旧版：仅点云近邻颜色分区'),('after-filled.jpg','新版：照片辅助分区后的统一填色'),('measured.jpg','照片与点云颜色证据（保留拍摄明暗，非最终填色）'),('regions.jpg','新版色区标签示意（示意色不是实物颜色）')])
        links=''.join(f'<a href="{ident}/rgb-segmentation/{p.name}" target="_blank">投影核对 {n+1}</a> ' for n,p in enumerate(sorted(out.glob('projection-*.jpg'))))
        rows=''.join(f'<span>{html.escape(g["name"])} · {g["faces"]:,} 面</span>' for g in r['regions'])
        sections.append(f'<section id="{ident}"><h2>{html.escape(r["name"])}</h2><p>{evidence}</p><div class="pair">{figures}</div><div class="tags">{rows}</div><p><a class="button" href="/#exhibit/{ident}">进入展品，旋转查看 / 自选上色 →</a> <a href="{ident}/rgb-segmentation/report.json">处理报告</a></p><details><summary>查看真实照片与模型轮廓核对</summary>{links}</details></section>')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SCAN3D · 多视角照片辅助色区</title><style>body{margin:0;background:#f6f4ee;color:#35443c;font:15px/1.7 "Segoe UI","Microsoft YaHei",sans-serif}main{max-width:1500px;margin:auto;padding:36px}h1,h2{font-weight:500}.pair{display:grid;grid-template-columns:1fr 1fr;gap:14px}section{background:white;border:1px solid #e1e3db;border-radius:16px;padding:24px;margin:24px 0}figure{margin:0}img{width:100%}figcaption{font-size:13px;color:#68796c}a{color:#476d60}.method{padding:20px;background:#e8ede4;border-radius:12px}.tags{display:flex;gap:10px;flex-wrap:wrap;padding:12px 0}.tags span{background:#f2f3ee;border-radius:7px;padding:4px 10px}.button{display:inline-block;padding:8px 16px;background:#e8ede4;border-radius:8px}details a{margin-right:16px}@media(max-width:800px){main{padding:16px}.pair{grid-template-columns:1fr}}</style><main><a href="/">← 陈列柜</a><h1>让颜色回到原来的位置。</h1><p>同一模型、同一视角，比较点云分区与多视角照片辅助分区。下方颜色组可在展品中分别改色。</p><div class="method">归档三维点恢复拍摄坐标 → 相机投影 / 深度遮挡检查 → SLIC 与保边降噪 → 较正视角加权中位数融合 → Lab 色区与深色 / 粉红细节保护 → 表面邻接优化。<br>未使用生成式 AI，不替换模型，不改动原始 STL、点云或扫描系统。底面无照片证据时保留未知。小字、细线仍受展示网格三角面大小限制；交互展品已加入「颜色边缘平滑」开关，默认开启；下方静态图保留硬标签，便于检查分区。平滑可减轻锯齿感，不能纠正误分区。</div>'''+''.join(sections)+'</main></html>'
    (PUBLIC/'rgb-segmentation.html').write_text(page,encoding='utf8')

if __name__=='__main__':
    from segment_colors import ROOT
    write_photo_audit(json.loads((ROOT/'assets/rgb-segmentation-report.json').read_text(encoding='utf8')))
