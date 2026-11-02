"""Bounded scan cleanup. Preview binds an expiring nonce to an exact file manifest.

Called only by the local broker while holding the existing scan/device lock.
No path, file list, or shell command is accepted from the client.
"""
import hashlib,json,os,re,secrets,shutil,stat,time
from collections import Counter
from pathlib import Path

class Cleanup:
 def __init__(self,data,published):
  self.data=Path(data).resolve();self.published=Path(published).resolve();self.pending={}

 def _tree(self,root,base):
  if root.is_symlink() or root.resolve().parent!=base or not root.is_dir():
   raise ValueError('目录边界检查失败，拒绝删除')
  entries=[]
  for here,dirs,files in os.walk(root,followlinks=False):
   for p in [Path(here)]+[Path(here)/x for x in files]:
    s=p.lstat()
    if stat.S_ISLNK(s.st_mode) or not (stat.S_ISREG(s.st_mode) or stat.S_ISDIR(s.st_mode)):
     raise ValueError('存在链接或特殊文件，请人工检查后再清理')
    if p.is_mount() or s.st_dev!=root.stat().st_dev:raise ValueError('目录包含挂载点，拒绝删除')
    entries.append((p,s))
   for d in dirs:
    if (Path(here)/d).is_symlink():raise ValueError('目录包含符号链接，拒绝删除')
  return entries

 def _plan(self,name,mode):
  if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',name):raise ValueError('无效扫描编号')
  if mode not in ('photos','all'):raise ValueError('无效清理类型')
  root=self.data/name
  if root.is_symlink() or not root.is_dir():raise ValueError('扫描不存在')
  try:status=json.loads((root/'status.json').read_text())
  except (OSError,ValueError):raise ValueError('不是有效的扫描档案')
  if not isinstance(status,dict) or not ((root/'bundle').is_dir() or any(root.glob('**/combined.npz'))):
   raise ValueError('不是有效的扫描档案')
  entries=self._tree(root,self.data);roots=[root]
  if mode=='photos':
   # Only source capture images; never infer deletable data from extensions alone.
   entries=[(p,s) for p,s in entries if re.fullmatch(r'position-\d{3,4}/(OFF|A|B|COLOR)/same-frame\.(png|ppm)',p.relative_to(root).as_posix())]
  else:
   public=self.published/name
   if public.exists() or public.is_symlink():
    entries+=self._tree(public,self.published);roots.append(public)
  files=[(p,s) for p,s in entries if stat.S_ISREG(s.st_mode)]
  fingerprint=hashlib.sha256(json.dumps(sorted((str(p),s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_mode) for p,s in entries)).encode()).hexdigest()
  logical=sum(s.st_size for _,s in files)
  allocated=sum(getattr(s,'st_blocks',(s.st_size+511)//512)*512 for _,s in files if s.st_nlink==1)
  return dict(name=name,mode=mode,roots=roots,files=files,fingerprint=fingerprint,bytes=logical,estimated_reclaim_bytes=allocated,
    count=len(files),types=dict(Counter(p.suffix.lower() or '(无扩展名)' for p,_ in files)))

 def preview(self,name,mode):
  p=self._plan(name,mode);now=time.monotonic()
  self.pending={k:v for k,v in self.pending.items() if v['expires']>now}
  if len(self.pending)>=64:self.pending.pop(next(iter(self.pending)))
  token=secrets.token_hex(24);self.pending[token]=dict(name=name,mode=mode,fingerprint=p['fingerprint'],expires=now+600)
  return dict(token=token,name=name,mode=mode,count=p['count'],bytes=p['bytes'],estimated_reclaim_bytes=p['estimated_reclaim_bytes'],types=p['types'],
    roots=[str(x) for x in p['roots']],examples=[str(x.relative_to(self.data/name)) if x.is_relative_to(self.data/name) else str(x) for x,_ in p['files'][:6]],expires_seconds=600,
    scope='仅各采集位置 OFF/A/B/COLOR 的 same-frame.png/ppm 原图；保留点云、STL、标定、报告和其他副本。' if mode=='photos' else '删除该扫描目录全部文件，以及同名已发布结果目录（如存在）。不同名的历史派生模型、电脑或外置存储副本不在此范围。')

 def execute(self,name,mode,token,confirm,acknowledged):
  saved=self.pending.get(token) if isinstance(token,str) else None
  if not saved or saved['expires']<time.monotonic() or saved['name']!=name or saved['mode']!=mode:
   raise ValueError('预览已失效，请重新查看删除范围')
  if confirm!=name or acknowledged is not True:raise ValueError('请完整输入扫描编号并确认不可恢复')
  p=self._plan(name,mode)
  if p['fingerprint']!=saved['fingerprint']:raise ValueError('文件已变化，请重新预览后确认')
  if not p['count']:raise ValueError('没有可删除的文件')
  # Durable write-ahead audit outside the deleted run; token is single-use.
  log=self.data/'scan3d-cleanup-log';log.mkdir(exist_ok=True)
  if log.is_symlink() or log.resolve().parent!=self.data:raise ValueError('日志路径异常')
  record=dict(name=name,mode=mode,time=time.time(),count=p['count'],bytes=p['bytes'],roots=[str(x) for x in p['roots']],status='started')
  path=log/(secrets.token_hex(16)+'.json')
  def save():
   with path.open('w') as f:json.dump(record,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
  save();del self.pending[token];before=shutil.disk_usage(self.data).free;removed=0
  try:
   if mode=='photos':
    for file,_ in p['files']:file.unlink();removed+=1
   else:
    for root in reversed(p['roots']):shutil.rmtree(root)
    removed=p['count']
   record.update(status='complete',removed_files=removed,free_bytes_after=shutil.disk_usage(self.data).free);save()
   return dict(deleted=True,name=name,mode=mode,removed_files=removed,free_delta_bytes=record['free_bytes_after']-before,free_bytes=record['free_bytes_after'],audit=str(path))
  except Exception as e:
   record.update(status='partial_failure',removed_files=removed,error=str(e));save()
   raise ValueError('清理中断，可能已有部分文件删除；请重新预览剩余文件。日志：'+str(path)) from e
