"""Bounded, offline Screened Poisson worker; operates on immutable saved points."""
import os,sys,json,time,hashlib,subprocess,signal,resource,traceback,fcntl
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parent/'mesh-vendor'),'/opt/afc03-scanner/surface-repair/v1/vendor']
import numpy as np,trimesh
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import minimum_spanning_tree,connected_components
from common import DATA,read
from mesh_input import digest,load_xyz,voxel_indices,metadata
from mesh_finish import finish_mesh

from chat_priority import priority_operation

@priority_operation
def run(out):
 start=time.monotonic();req=read(out/'request.json');stages={};last=start;child=None;peak_child=0
 def mark(stage):
  nonlocal last
  now=time.monotonic();stages[stage]=round(now-last,6);last=now
  tmp=out/'state.tmp';tmp.write_text(json.dumps(dict(status='running',stage=stage,elapsed_seconds=now-start)));tmp.replace(out/'state.json');check()
 def check():
  if (out/'STOP').exists():raise InterruptedError('用户已取消；原始点云保留')
 def finish(status,**extra):
  tmp=out/'state.tmp';tmp.write_text(json.dumps(dict(status=status,stage=status,elapsed_seconds=time.monotonic()-start,**extra)));tmp.replace(out/'state.json')
 try:
  if 'SCAN3D_MESH_LOCK_FD' in os.environ:lock=os.fdopen(int(os.environ['SCAN3D_MESH_LOCK_FD']),'r')
  else:lock=open('/run/lock/afc03-fpga-scan.lock','r');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  depth=req.get('depth',7 if req['quality']=='standard' else 8);samples=req.get('samples_per_node',2)
  if type(depth) is not int or not 4<=depth<=8 or type(samples) is not int or samples not in (2,8,16):raise ValueError('无效的深度或降噪参数')
  source=Path(req['source_path']).resolve();root=DATA/req['run'];sha=digest(source)
  mark('load');x=load_xyz(source)
  if np.max(np.ptp(x,axis=0))>2000:raise ValueError('坐标范围异常，请核对毫米单位')
  cfg={};bundle=None
  for b in (root/'bundle',root/'source/bundle'):
   if (b/'axis.json').exists():bundle=b;cfg=read(b/'config.json');break
  ground=read(bundle/'turntable_filter.json') if bundle else {}
  if ground.get('enabled') and ground.get('axis_sha256') and hashlib.sha256((bundle/'axis.json').read_bytes()).hexdigest()!=ground['axis_sha256']:raise ValueError('转盘高度与轴标定不匹配，请先重新验证标定')
  cut=ground.get('min_axis_y_mm') if ground.get('enabled') else None
  if req['cap_base'] and cut is None:raise ValueError('所选扫描缺少已标定转盘高度，不能自动封底')
  mark('voxel');voxel=.4 if req['quality']=='standard' else .25
  ix,ground_removed=voxel_indices(x,voxel,cut,check);voxel_points=len(ix)
  maximum=65000 if req['quality']=='standard' else 100000
  if len(ix)>maximum:ix=ix[np.linspace(0,len(ix)-1,maximum).astype(int)]
  p=x[ix];tree=cKDTree(p);dist,_=tree.query(p,k=min(17,len(p)),workers=1);d=dist[:,1:].mean(1);limit=max(1.,float(np.median(d)+3*1.4826*np.median(abs(d-np.median(d)))))
  good=d<limit;removed=int((~good).sum());ix=ix[good];p=x[ix]
  if len(p)<300:raise ValueError('去噪后有效点不足')
  mark('prepare');tree=cKDTree(p);normals=np.empty_like(p)
  k=min(40,len(p))
  for begin in range(0,len(p),5000):
   check();_,neighbors=tree.query(p[begin:begin+5000],k=k);q=p[neighbors];q-=q.mean(1)[:,None,:];_,vec=np.linalg.eigh(np.einsum('nki,nkj->nij',q,q));normals[begin:begin+len(q)]=vec[:,:,0]
  inferred,positions=metadata(source,ix,len(x));oriented=np.zeros(len(p),bool);angle_sources={}
  if bundle:
   axis=read(bundle/'axis.json');center=np.asarray(axis['axis_point_closest_to_camera_origin_mm']);direction=np.asarray(axis['axis_direction_for_positive_pulses_camera']);direction/=np.linalg.norm(direction)
   ex=np.array([1.,0,0]);ex-=direction*(ex@direction);ex/=np.linalg.norm(ex);basis=np.stack([ex,direction,np.cross(ex,direction)],axis=1)
   for pos in np.unique(positions[~inferred]):
    if pos<0:continue
    j=int(pos);header=read(root/f'position-{j:03d}/A/frame.json') or read(root/f'source/position-{j:03d}/A/frame.json');angle=header.get('angle',{})
    degrees=None
    if angle.get('source')=='commanded_pulses_no_encoder':degrees=(angle['emitted_after']-angle['zero_pulses'])*360/angle['pulses_per_revolution'];angle_sources[str(j)]='saved_frame_pulses'
    elif 'angle_schedule' in cfg and j<len(cfg['angle_schedule']):degrees=cfg['angle_schedule'][j]*360/3200;angle_sources[str(j)]='saved_angle_schedule'
    if degrees is None:continue
    camera=(-center@Rotation.from_rotvec(direction*np.deg2rad(degrees)).as_matrix())@basis
    ids=np.flatnonzero((positions==pos)&~inferred);flip=np.einsum('ij,ij->i',normals[ids],camera-p[ids])<0;normals[ids[flip]]*=-1;oriented[ids]=True
  orientation='saved_camera_views'
  if oriented.any():
   ids=np.flatnonzero(~oriented);nearest=cKDTree(p[oriented]).query(p[ids])[1];ref=normals[oriented][nearest];normals[ids[np.einsum('ij,ij->i',normals[ids],ref)<0]]*=-1
  else:
   # Fallback for legacy clouds without per-view provenance; report explicitly.
   orientation='neighbor_mst_outward_heuristic';_,nn=tree.query(p,k=min(9,len(p)));r=np.repeat(np.arange(len(p)),nn.shape[1]-1);c=nn[:,1:].ravel();w=1-np.abs(np.einsum('ij,ij->i',normals[r],normals[c]))+1e-6
   graph=coo_matrix((w,(r,c)),shape=(len(p),len(p))).tocsr();mst=minimum_spanning_tree(graph);adj=(mst+mst.T).tocsr();seen=np.zeros(len(p),bool)
   for seed in range(len(p)):
    if seen[seed]:continue
    stack=[seed];seen[seed]=True;component=[]
    while stack:
     i=stack.pop();component.append(i)
     for j in adj.indices[adj.indptr[i]:adj.indptr[i+1]]:
      if not seen[j]:
       if normals[i]@normals[j]<0:normals[j]*=-1
       seen[j]=True;stack.append(j)
    if np.einsum('ij,ij->i',normals[component],p[component]-p.mean(0)).sum()<0:normals[component]*=-1
  mark('normals');confidence=np.where(inferred,.25,1.)
  np.c_[p,normals*confidence[:,None]].astype('<f4').tofile(out/'oriented.bnpts')
  executable=Path(__file__).resolve().parent/'bin/PoissonRecon'
  command=[str(executable),'--in',str(out/'oriented.bnpts'),'--out',str(out/'poisson.ply'),'--depth',str(depth),'--fullDepth',str(min(5,depth)),'--threads','2','--confidence','1','--samplesPerNode',str(samples),'--pointWeight','4','--scale','1.1','--performance']
  def memory_limit():resource.setrlimit(resource.RLIMIT_AS,(900*1024**2,900*1024**2))
  with (out/'poisson.log').open('wb') as log:child=subprocess.Popen(command,cwd=out,stdout=log,stderr=log,stdin=subprocess.DEVNULL,preexec_fn=memory_limit)
  while child.poll() is None:
   check()
   if time.monotonic()-start>240:raise TimeoutError('板端 STL 任务超过 240 秒限制')
   try:
    line=next(v for v in Path(f'/proc/{child.pid}/status').read_text().splitlines() if v.startswith('VmRSS:'));rss=int(line.split()[1]);peak_child=max(peak_child,rss)
    if rss>650*1024:raise MemoryError('重建程序超过 650 MiB 内存限制，请降低深度或选标准采样')
   except (FileNotFoundError,StopIteration):pass
   time.sleep(.1)
  if child.returncode or not (out/'poisson.ply').is_file():raise RuntimeError('Poisson 重建失败：'+(out/'poisson.log').read_text(errors='replace')[-700:])
  mark('poisson');m=trimesh.load(out/'poisson.ply',process=True,force='mesh');m.update_faces(m.unique_faces());m.update_faces(m.nondegenerate_faces());m.remove_unreferenced_vertices();m.fix_normals()
  m,postprocess=finish_mesh(m,out,cut,req['cap_base'],req['close_small_holes'],req.get('cleanup','small'),check)
  check();m.export(out/'model-mm.stl');m.export(out/'model.ply')
  loaded=trimesh.load(out/'model-mm.stl',process=True,force='mesh');edges=np.bincount(loaded.edges_unique_inverse,minlength=len(loaded.edges_unique));mark('mesh_check')
  distances=cKDTree(x).query(loaded.vertices,workers=1)[0];back=cKDTree(loaded.vertices).query(x[np.linspace(0,len(x)-1,min(50000,len(x))).astype(int)],workers=1)[0]
  warnings=['曲面与补洞区域包含几何推断，不代表新增实测数据','自交检测尚未执行；封闭性通过不代表可直接打印或尺寸准确']
  if not loaded.is_watertight:warnings.append('网格尚未完全封闭；可检查缺口或选择已标定平面封底')
  if orientation!='saved_camera_views':warnings.append('历史点云缺少可用视角记录，法向使用邻域一致性与向外启发式')
  if distances.max()>2:warnings.append('部分网格顶点距离输入点云超过 2 mm，请重点审阅推断区域')
  report=dict(algorithm='Screened Poisson 13.72',learned_model=False,host='RK3576',source_sha256=sha,source=req['source'],source_run=req['run'],units='mm',coordinate_transform='none',input_points=len(x),input_bounds_mm=np.ptp(x,axis=0).tolist(),meshing_points=len(p),voxel_points=voxel_points,preprocessing='chunked_voxel_first_point_v1',input_limit_points=8000000,meshing_bounds_mm=np.ptp(p,axis=0).tolist(),voxel_mm=voxel,ground_removed=ground_removed,outliers_removed=removed,outlier_threshold_mm=limit,normal_orientation=orientation,viewpoint_positions=len(angle_sources),inferred_input_points=int(inferred.sum()),inferred_normal_weight=.25,depth=depth,samples_per_node=samples,threads=2,small_hole_repair=req['close_small_holes'],base_capped=req['cap_base'],base_is_estimated=req['cap_base'],ground_cutoff_mm=cut,components_removed=postprocess['components_removed'],vertices=len(loaded.vertices),triangles=len(loaded.faces),mesh_bounds_mm=loaded.bounds.tolist(),mesh_extents_mm=loaded.extents.tolist(),watertight=bool(loaded.is_watertight),winding_consistent=bool(loaded.is_winding_consistent),boundary_edges=int((edges==1).sum()),nonmanifold_edges=int((edges>2).sum()),self_intersections_checked=False,vertex_to_input_mm={str(q):float(np.percentile(distances,q)) for q in (50,95,99,100)},input_to_vertex_mm={str(q):float(np.percentile(back,q)) for q in (50,95,99,100)},distance_metric='nearest vertex/point; not exact point-to-triangle distance or absolute accuracy',stages_seconds=stages,elapsed_seconds=time.monotonic()-start,worker_peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,poisson_peak_rss_mib=peak_child/1024,original_cloud_unchanged=digest(source)==sha,warnings=warnings)
  report.update(postprocess)
  if req.get('cleanup')=='main':report['warnings'].append('仅保留最大连通主体；真实但断开的附件也可能被移除，可下载原始网格与移除部分复核')
  assert report['original_cloud_unchanged'];(out/'mesh-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));finish('complete')
 except BaseException as e:
  if child and child.poll() is None:child.terminate();child.wait(timeout=5)
  finish('cancelled' if isinstance(e,InterruptedError) else 'failed',error=str(e));traceback.print_exc()
 finally:
  if 'lock' in locals():lock.close()
if __name__=='__main__':run(Path(sys.argv[1]))
