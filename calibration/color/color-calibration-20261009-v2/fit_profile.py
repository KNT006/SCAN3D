"""16-swatch trial. Same LED8 settings; old JPEG + new full RGB observations.

Regularized affine model with white and orange/yellow hue constraints.
Catalogue/tag RGB values are approximate display references, not reflectance.
"""
from pathlib import Path
import json, colorsys
import cv2
import numpy as np

P=Path(__file__).resolve().parent
OLD=P.parent/'color-calibration-20261009'
previous=json.loads((OLD/'profile.json').read_text(encoding='utf-8'))
records=json.loads((P/'observations.json').read_text())
fit=[r for r in records if r['hex']]
ids=np.array([r['id'] for r in fit])
X=np.c_[[r['rgb'] for r in fit],np.full(len(fit),255)]/255
T=np.array([[int(r['hex'][i:i+2],16) for i in (1,3,5)] for r in fit])/255*(220/255)
weights=np.where(np.isin(ids,['30100','30102']),3,1)
identity=np.vstack([np.eye(3),np.zeros(3)])
A=np.kron(X,np.eye(3)); w=np.repeat(weights,3)
reg=np.diag(np.repeat([.03,.03,.03,.12],3))
normal=A.T@(w[:,None]*A)+reg
rhs=A.T@(w*T.flatten())+reg@identity.flatten()
constraints=[]; values=[]
white=X[ids=='30100'].mean(axis=0)
for channel in range(3):
    constraints.append(np.kron(white,np.eye(3)[channel]));values.append(220/255)
for code in ['12300','30400']:
    i=np.flatnonzero(ids==code)[0];target=T[i]
    # Both warm references have R >= G >= B; constrain (G-B)/(R-B).
    alpha=(target[1]-target[2])/(target[0]-target[2])
    constraints.append(np.kron(X[i],[-alpha,1,alpha-1]));values.append(0)
C=np.array(constraints)
kkt=np.block([[normal,C.T],[C,np.zeros((len(C),len(C)))]])
fitted=np.linalg.solve(kkt,np.r_[rhs,values])[:12].reshape(4,3)
strength=.65
matrix=identity*(1-strength)+fitted*strength
assert np.max(np.abs(matrix))<4 and np.isfinite(matrix).all()
pred=X@matrix
hue=lambda v:colorsys.rgb_to_hsv(*np.clip(v,0,255))[0]*360
for r in records:
    src=np.r_[r['rgb'],255]/255
    r['v1_rgb']=np.clip(src@np.array(previous['matrix_rgb']).T*255,0,255).round(2).tolist()
    r['v2_rgb']=np.clip(src@matrix*255,0,255).round(2).tolist()
    r['hue_deg']={k:hue(r[k]) for k in ['rgb','v1_rgb','v2_rgb']}
    r['reference_kind']='unverified' if not r['hex'] else 'community_RFID_readout' if r['id']=='12300' else 'manufacturer_catalog_HEX'
profile=dict(previous)
profile.update(id='bambu-sixteen-20261009-v2',title='16 色样片试用校正 · 橙黄保护',
    matrix_rgb=matrix.T.tolist(),strength=strength,white_target=220,led=8,
    patch_count=16,fit_patch_count=14,fit_observation_count=len(fit),
    conditions='白灯 8 / 增益 50 / 激光关闭；同样的环境光和样片摆放平面',
    source='old_LED8_preview_JPEG_3_frames_plus_new_LED8_full_RGB_PPM_5_frames',
    status='provisional_catalog_and_tag_reference',patch_results=records,
    hue_constraints=['12300','30400'],regularization=[.03,.03,.03,.12],
    white_constraint='mean of two white observations; target 220 before 65% blend',
    limitation='13 色厂商 HEX + 1 色社区原始 RFID 读出作为近似参考；旧灰黑待核实。非标准测色标定；两批样片位置/格式不同，白灰观测存在差异。仅预览，原图和扫描颜色不变。',
    fit_reference_rgb_rmse_before=float(np.sqrt(np.mean((X[:,:3]-T)**2))*255),
    fit_reference_rgb_rmse_after=float(np.sqrt(np.mean((np.clip(pred,0,1)-T)**2))*255),
    model_selection_note='Compared affine and root-polynomial fits. Unconstrained leave-one-color-out RGB RMSE ~35.78 vs 35.05; retained simpler affine, added orange/yellow hue guards. Final constrained fit still requires independent object validation.',
    sources=previous['sources']+['https://bambu-lab-global.myshopify.com/products/pla-basic-filament',
       'https://github.com/queengooborg/Bambu-Lab-RFID-Library/tree/main/PLA/PLA%20Tough/Orange'],
    orange_reference_provenance=json.loads((P/'orange-reference-provenance.json').read_text()))
image=cv2.imread(str(P/'new-colors-0.ppm'))[:,:,::-1]
out=cv2.transform(image.astype(np.float32),matrix.T[:,:3].astype(np.float32))+matrix.T[:,3]*255
profile['full_frame_out_of_range_fraction']=float(np.mean(np.any((out<0)|(out>255),axis=-1)))
cv2.imwrite(str(P/'original-preview.jpg'),image[:,:,::-1])
cv2.imwrite(str(P/'corrected-preview.jpg'),np.clip(out,0,255).astype(np.uint8)[:,:,::-1])
oldmatrix=np.array(previous['matrix_rgb'])
v1=cv2.transform(image.astype(np.float32),oldmatrix[:,:3].astype(np.float32))+oldmatrix[:,3]*255
cv2.imwrite(str(P/'v1-same-input.jpg'),np.clip(v1,0,255).astype(np.uint8)[:,:,::-1])
(P/'profile.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8')
for r in records:
    if r['capture']=='new_led8_ppm':print(r['id'],r['rgb'],'->',r['v2_rgb'],r['hue_deg'])
print('RGB fitting residual',profile['fit_reference_rgb_rmse_before'],profile['fit_reference_rgb_rmse_after'],'out-of-range',profile['full_frame_out_of_range_fraction'])
