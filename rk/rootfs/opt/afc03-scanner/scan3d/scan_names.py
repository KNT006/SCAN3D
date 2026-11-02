"""Editable scan labels; acquisition IDs and binary data remain stable."""
import json, os, re, tempfile, unicodedata
from common import read


def validate_title(value):
 if not isinstance(value,str):raise ValueError('请输入模型名称')
 value=value.strip()
 if not value or len(value)>80:raise ValueError('模型名称须为 1–80 个字符')
 if any(unicodedata.category(c).startswith('C') for c in value):raise ValueError('模型名称不能包含控制字符')
 return value


def title_for(path):
 state=read(path/'status.json')
 return state.get('title') or state.get('object_name') or path.name


def export_stem(path):
 title=re.sub(r'[<>:"/\\|?*]', '_', title_for(path)).strip(' .')[:80] or 'model'
 return title+'-'+path.name


def named_report(path,document):
 """Label exported reports without rewriting acquisition evidence."""
 title=title_for(path)
 def relabel(value):
  if isinstance(value,dict):return {k:title if k in ('title','object_name') else relabel(v) for k,v in value.items()}
  if isinstance(value,list):return [relabel(v) for v in value]
  return value
 result=relabel(document)
 if isinstance(result,dict):result.update(title=title,scan_id=path.name)
 return result


def rename_scan(path,value):
 title=validate_title(value)
 target=path/'status.json'
 state=json.loads(target.read_text(encoding='utf-8'))
 if not isinstance(state,dict):raise ValueError('扫描状态记录无效')
 state.setdefault('original_title',state.get('title') or state.get('object_name') or path.name)
 state.update(title=title,object_name=title)
 fd,tmp=tempfile.mkstemp(prefix='.rename-',suffix='.tmp',dir=path)
 try:
  with os.fdopen(fd,'w',encoding='utf-8') as stream:
   json.dump(state,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
  os.chmod(tmp,target.stat().st_mode & 0o777)
  os.replace(tmp,target)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
 return dict(id=path.name,title=title)
