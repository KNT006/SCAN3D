"""Reproducible, provisional display-space fit; catalogue RGB is not colorimetry."""
from pathlib import Path
import json
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
ids = ['30100','30102','30601','12102','12101','30200','40500','30602','40501']
names = ['白','灰','蓝灰','旧版深灰','旧版黑','红','绿','湖蓝','薄荷青']
hexes = ['FFFFFF','9EA2A2','688197',None,None,'D6001C','00AE42','0069B1','7AE1BF']
centers = json.loads((ROOT/'lighting-test.json').read_text())['centers']
frames = [cv2.imread(str(ROOT/f'calibration-{i}.ppm'))[:,:,::-1] for i in range(5)]
medians = np.array([[np.median(f[y*2-24:y*2+24,x*2-24:x*2+24],axis=(0,1)) for x,y in centers] for f in frames])
observed = np.median(medians,axis=0)/255
indices = [i for i,h in enumerate(hexes) if h]
targets = np.array([[int(hexes[i][j:j+2],16) for j in (0,2,4)] for i in indices])/255*(240/255)
src = np.c_[observed[indices],np.ones(len(indices))]
weights = np.diag([1,8,3,1,1,1,1])
regularization = np.diag([.03,.03,.03,.12])
identity = np.vstack([np.eye(3),np.zeros(3)])
normal = src.T@weights@src+regularization
rhs = src.T@weights@targets+regularization@identity
# Exact white headroom anchor, weighted gray / blue-gray, regularized affine RGB.
kkt = np.block([[normal,src[:1].T],[src[:1],np.zeros((1,1))]])
fitted = np.linalg.solve(kkt,np.vstack([rhs,targets[0]]))[:4]
# Conservative preview strength. No change to saved RGB, stripe or geometry paths.
strength = .65
matrix = identity*(1-strength)+fitted*strength
predicted = np.c_[observed,np.ones(9)]@matrix
patches = []
for i,(x,y) in enumerate(centers):
    values=np.array([f[y*2-24:y*2+24,x*2-24:x*2+24] for f in frames])
    patches.append(dict(id=ids[i],name=names[i],upright_row=i//3,upright_col=i%3,
        raw_roi=[x*2-24,y*2-24,48,48],catalog_hex=('#'+hexes[i]) if hexes[i] else None,
        role='approximate_fit' if hexes[i] else 'observed_only_reference_unverified',
        median_rgb=(observed[i]*255).tolist(),frame_range_rgb=np.ptp(medians[:,i],axis=0).tolist(),
        corrected_rgb=(np.clip(predicted[i],0,1)*255).round(2).tolist(),
        saturated_fraction=float(np.mean(np.any(values>=250,axis=-1)))))
profile=dict(version=1,id='bambu-nine-20261009-v1',title='9 色样片试用校正',
    status='provisional_catalog_reference',processor='RK CPU',domain='encoded_RGB_8bit_affine',
    source='full_resolution_RGB_PPM_not_sensor_RAW',matrix_rgb=matrix.T.tolist(),
    strength=strength,white_target=240,gain=50,led=12,led_count=35,
    patch_count=9,fit_patch_count=7,unverified_reference_ids=['12102','12101'],
    conditions='白灯 12 / 增益 50 / 激光关闭；相同照明与相机设置',
    limitation='厂商 HEX 为显示参考，非样片实测 Lab。未验证真实色差；仅校正预览，原图、点云颜色与条纹路径不变。',
    sources=['https://bambu-lab-global.myshopify.com/products/petg-basic',
             'https://bambu-lab-global.myshopify.com/products/abs-filament'],
    patch_results=patches,
    fit_reference_rgb_rmse_before=float(np.sqrt(np.mean((observed[indices]-targets)**2))*255),
    fit_reference_rgb_rmse_after=float(np.sqrt(np.mean((predicted[indices]-targets)**2))*255),
    metric_note='Same-sample catalogue-fit RGB residual, not independent accuracy or Delta E')
(ROOT/'profile.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8')
# Evidence images are pipeline outputs, not replacements for the original PPM files.
rgb=frames[0];corrected=cv2.transform(rgb.astype(np.float32),matrix.T[:,:3].astype(np.float32))+matrix.T[:,3]*255
profile['full_frame_out_of_range_fraction']=float(np.mean(np.any((corrected<0)|(corrected>255),axis=-1)))
cv2.imwrite(str(ROOT/'corrected-preview.jpg'),np.clip(corrected,0,255).astype(np.uint8)[:,:,::-1])
cv2.imwrite(str(ROOT/'original-preview.jpg'),rgb[:,:,::-1])
(ROOT/'profile.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:profile[k] for k in ['fit_reference_rgb_rmse_before','fit_reference_rgb_rmse_after','full_frame_out_of_range_fraction']}))
