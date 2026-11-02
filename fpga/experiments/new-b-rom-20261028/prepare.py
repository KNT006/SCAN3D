from pathlib import Path
import json,sys,hashlib,shutil
from types import SimpleNamespace
import numpy as np
ROOT=Path(__file__).resolve().parents[3];WORK=Path('D:/PCle/_b28');HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT/'rk/rootfs/opt/afc03-scanner/fpga'))
from spatial_reference import spatial_lut,certainly_outside
base=ROOT/'diagnostics/20261027-b-recalibration/captures/baseline';bundle=HERE/'bundle';shutil.copytree(base,bundle,dirs_exist_ok=True)
cam=json.loads((base/'camera.json').read_text());axis=json.loads((base/'axis.json').read_text());planes=json.loads((base/'planes.json').read_text());candidate=json.loads((ROOT/'diagnostics/20261027-b-recalibration/candidate-validation.json').read_text())
def generate(planes):
 a=SimpleNamespace(camera=cam,axis=axis,planes=planes['planes']);words=[0]*4096;pixels=0
 for role,label in enumerate(['A','B']):
  for start in range(0,1920,64):
   known,rad=spatial_lut(a,[0,start,1080,min(start+64,1920)],label,70)
   for i in range(len(known)):
    outside=known[i]&(rad[i]>70);bad=np.r_[0,np.cumsum(~outside)];x=np.arange(1080);mask=(bad[np.minimum(x+12,1080)]-bad[np.maximum(x-11,0)])==0
    edge=np.diff(np.r_[False,mask,False].astype(int));ranges=list(zip(np.flatnonzero(edge==1),np.flatnonzero(edge==-1)-1));assert len(ranges)<=2
    word=0;restore=np.zeros(1080,bool)
    for j,(lo,hi) in enumerate(ranges+[(4095,0)]*(2-len(ranges))):word|=int(lo)<<(j*24);word|=int(hi)<<(j*24+12);restore|=(x>=lo)&(x<=hi)
    assert np.array_equal(restore,mask)
    for k in [0,11,140,409,874,1068,1079]:assert bool(mask[k])==certainly_outside(known[i],rad[i],k,10,70)
    words[role*2048+start+i]=word;pixels+=int(mask.sum())
 return words,pixels
old,_=generate(planes);baseline=ROOT/'fpga/source/fpga-gain-handshake-20261013/rtl/spatial_mask.hex';assert old==[int(s,16) for s in baseline.read_text().split()],'baseline ROM mismatch'
planes['planes']['laser_B']={k:candidate[k] for k in ['normal_camera','offset_mm_n_dot_X_equals_offset','camera_sha256','training_p95_max_mm','held_out_p95_max_mm']};planes['planes']['laser_B']['source']='candidate-validation 20261027 11mm; user accepted 20261028';planes['absolute_accuracy_validated']=False
(bundle/'planes.json').write_text(json.dumps(planes,indent=2)+'\n');cfg=json.loads((bundle/'config.json').read_text());cfg['sha256']['planes.json']=hashlib.sha256((bundle/'planes.json').read_bytes()).hexdigest();(bundle/'config.json').write_text(json.dumps(cfg,indent=2)+'\n')
new,pixels=generate(planes);assert old[:2048]==new[:2048];rom=HERE/'spatial_mask.hex';rom.write_text(''.join(f'{w:012x}\n' for w in new),newline='\n')
target=WORK/'fpga-gain-handshake-20261013/rtl';shutil.copy2(rom,target/rom.name);p=target/'laser_full_row_core.v';s=p.read_text();s=s.replace('F:/AAA_FPGA/afc03-esp32-motor/fpga-rgb-adaptive-20261010/rtl/spatial_mask.hex',(target/'spatial_mask.hex').as_posix());p.write_text(s)
report=dict(baseline_rom_reproduced=True,A_unchanged=True,changed_B_rows=sum(a!=b for a,b in zip(old[2048:],new[2048:])),masked_pixels=pixels,rom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest(),calibration_hashes={k+'_sha256':hashlib.sha256((bundle/(k+'.json')).read_bytes()).hexdigest() for k in ['camera','axis','planes']},hardware_validated=False)
(HERE/'rom-validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
# Restore only missing IP outputs, verified against configurations from prior preparation.
restored=json.loads(Path('D:/PCle/_colorcache26/restored-ip-inputs.json').read_text());records=[]
for conf in restored['configs']:
 assert (WORK/conf['config']).read_bytes()==(Path('D:/PCle/_colorcache26')/conf['config']).read_bytes()
for item in restored['outputs']:
 dest=WORK/item['target'];donor=Path('D:/PCle/_colorcache26')/item['target'];assert hashlib.sha256(donor.read_bytes()).hexdigest()==item['sha256']
 if dest.exists():assert dest.read_bytes()==donor.read_bytes()
 else:dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(donor,dest)
 records.append(item)
(HERE/'restored-ip-inputs.json').write_text(json.dumps(records,indent=2));print('IP outputs validated',len(records))

