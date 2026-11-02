from pathlib import Path
import json,re,os
DATA=Path('/userdata/afc03-scanner/jobs')
CODE=Path('/opt/afc03-scanner/scan3d')
FPGA=Path('/opt/afc03-scanner/fpga')
def read(p,default=None):
 try:return json.loads(p.read_text())
 except (OSError,ValueError):return {} if default is None else default
def job(name):
 if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',name):raise ValueError('无效扫描编号')
 p=DATA/name
 if not p.is_dir() or p.is_symlink():raise ValueError('扫描不存在')
 return p
def active():
 boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
 for p in DATA.iterdir():
  s=read(p/'status.json')
  if s.get('status')=='running' and s.get('boot_id')==boot:
   try:
    cmd=(Path('/proc')/str(int(s['pid']))/'cmdline').read_bytes()
    if b'/opt/afc03-scanner/' in cmd or str(p/'resume-audit/resume_runner.py').encode() in cmd.split(b'\0'):return p
   except (OSError,KeyError,ValueError):pass
 return None
def camera_device():
 nodes=[Path('/dev')/p.parent.name for p in Path('/sys/class/video4linux').glob('video*/name') if 'milianke' in p.read_text().lower()]
 if len(nodes)!=1:raise ValueError('未找到唯一的 FPGA 相机')
 return str(nodes[0])
PARAMS={
 'prominence':(18,1,100),'distance':(8,2,30),'signal_min':(40,1,255),
 'strong_width_max':(100,2,200),'weak_signal_below':(80,1,255),'weak_width_max':(65,2,200),
 'core_peak_fraction':(.7,.1,.95),'core_radius':(10,1,30),
 'neighbor_rows':(4,1,12),'min_support':(3,1,12),'dx_intercept':(2,0,20),'dx_per_row':(3,0,20),
 'rescue_strong':(80,1,255),'rescue_ratio':(3,1,10)}
def parameters(obj):
 if set(obj)-set(PARAMS):raise ValueError('未知条纹参数')
 out={}
 for k,(default,lo,hi) in PARAMS.items():
  v=obj.get(k,default)
  if isinstance(v,bool) or not isinstance(v,(float,int)) or not lo<=v<=hi:raise ValueError('参数超出范围: '+k)
  if isinstance(default,int) and int(v)!=v:raise ValueError('参数应为整数: '+k)
  out[k]=int(v) if isinstance(default,int) else v
 if out['min_support']>2*out['neighbor_rows']:raise ValueError('支持行数超出邻域')
 return out
