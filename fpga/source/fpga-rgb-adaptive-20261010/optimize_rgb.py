from pathlib import Path
p=Path(r'F:/AAA_FPGA/afc03-esp32-motor/fpga-rgb-adaptive-20261010/host/rgb_adaptive_strategy.py');s=p.read_text(encoding='utf-8-sig')
pos=s.index('\ndef supporters(')
s=s[:pos]+'''
def color_thresholds(color,records):
 if not records:return []
 ys=np.array([r['y'] for r in records]);xs=np.array([r['k'] for r in records])
 if np.any((ys<3)|(ys>=1917)|(xs<3)|(xs>=1077)):
  return [threshold(color,int(y),int(x)) for y,x in zip(ys,xs)]
 # Same 49 samples and exact median/percentile as the scalar oracle.
 dy,dx=np.mgrid[-3:4,-3:4]
 patches=color[ys[:,None]+dy.ravel(),xs[:,None]+dx.ravel()].astype(float)
 rgb=np.median(patches,axis=1);v=rgb.max(axis=1)
 spread=np.percentile(np.max(np.abs(patches-rgb[:,None,:]),axis=2),90,axis=1)
 reliable=(v>=12)&(v<245)&(spread<=35)
 suggested=np.floor(25+15*np.clip((v-100)/60,0,1)+.5).astype(int)
 return [dict(rgb=rgb[i].tolist(),v=float(v[i]),color_spread=float(spread[i]),color_reliable=bool(reliable[i]),color_threshold=int(suggested[i]),threshold=int(suggested[i]) if reliable[i] else 40) for i in range(len(records))]
''' +s[pos:]
s=s.replace("  r.update(threshold(color,r['y'],r['k']));raw.append(r)", "  raw.append(r)\n for r,t in zip(raw,color_thresholds(color,raw)):r.update(t)")
p.write_text(s,encoding='utf-8')
