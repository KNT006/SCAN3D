"""Cross-process locks for immutable scan readers versus cleanup."""
import fcntl,os,re
from pathlib import Path
from common import DATA

def acquire(name,exclusive=False):
 if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',name):raise ValueError('无效扫描编号')
 base=DATA/'scan3d-run-locks'
 if not base.is_dir() or base.is_symlink():raise ValueError('档案锁目录尚未初始化')
 path=base/(name+'.lock')
 try:
  fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o660)
  os.fchmod(fd,0o660)  # Broker and web service share the directory's setgid group.
 except FileExistsError:fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW)
 try:
  fcntl.flock(fd,(fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)|fcntl.LOCK_NB)
 except BlockingIOError:
  os.close(fd);raise ValueError('这份扫描正在分析或清理，请等待完成')
 except BaseException:
  os.close(fd);raise
 return fd
