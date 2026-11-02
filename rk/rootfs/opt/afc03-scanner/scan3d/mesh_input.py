"""Bounded preprocessing for dense scans; never edits the source archive."""
import hashlib,zipfile
from pathlib import Path
import numpy as np
MAX_INPUT_POINTS=8_000_000
MAX_VOXELS=400_000
CHUNK=100_000

def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()

def load_xyz(source):
 # Inspect the array header before allocating the decompressed coordinate array.
 with zipfile.ZipFile(source) as z:
  key=next((k for k in ('xyz','axis_frame_mm') if k+'.npy' in z.namelist()),None)
  if key is None:raise ValueError('点云缺少三维坐标')
  with z.open(key+'.npy') as f:
   version=np.lib.format.read_magic(f)
   if version==(1,0):shape,_,dtype=np.lib.format.read_array_header_1_0(f)
   elif version==(2,0):shape,_,dtype=np.lib.format.read_array_header_2_0(f)
   else:raise ValueError('不支持此点云数组格式')
   if len(shape)!=2 or shape[1]!=3 or dtype.kind not in 'fi' or not 300<=shape[0]<=MAX_INPUT_POINTS:raise ValueError('需要 300–8000000 个三维点；更大点云请在 PC 预处理')
 with np.load(source,allow_pickle=False) as d:x=np.asarray(d[key],dtype=np.float64)
 for begin in range(0,len(x),CHUNK):
  if not np.isfinite(x[begin:begin+CHUNK]).all():raise ValueError('点云含无效坐标')
 return x

def voxel_indices(x,voxel,cut=None,check=lambda:None):
 """Same first-point-per-voxel selection as a full np.unique, bounded scratch RAM."""
 ix=np.empty(0,dtype=np.int64);removed=0
 for begin in range(0,len(x),CHUNK):
  check();ids=np.arange(begin,min(begin+CHUNK,len(x)))
  if cut is not None:
   mask=x[ids,1]>cut;removed+=int((~mask).sum());ids=ids[mask]
  candidates=np.concatenate((ix,ids))
  _,first=np.unique(np.floor(x[candidates]/voxel).astype(np.int64),axis=0,return_index=True)
  ix=candidates[first]
  if len(ix)>MAX_VOXELS:raise ValueError('空间采样后仍超过 40 万点，请先选择标准采样或在 PC 处理；原始点云保留')
 return ix,removed

def metadata(source,ix,total):
 with np.load(source,allow_pickle=False) as d:
  def pick(key,default):
   if key not in d.files:return np.full(len(ix),default)
   a=d[key]
   if a.ndim!=1 or len(a)!=total:raise ValueError('点云来源标记长度不匹配')
   return a[ix]
  return pick('inferred',0).astype(bool),pick('position',-1)
