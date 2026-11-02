"""Read-only stage replay from versioned production candidates and saved points.

Uses production selectors, archived geometry decisions and saved RGB thresholds.
Fails closed if reconstructed selection differs from the saved point cloud.
"""
import json,time
import numpy as np
import cv2
from common import read,job
from rk_candidate_policy import VERSION,select_branch
from secondary_candidate_policy import decisions as secondary_decisions
from near_peak_policy import decisions as near_decisions


def archive_mode(report,header):
 version=report.get('version') or header.get('algorithm')
 if version==VERSION:return 'production'
 if version=='fpga-spatial25-rk-localrgb100-160-protected-v1':return 'historical'
 raise ValueError('暂不支持这份扫描的算法版本：'+str(version)+'；可在参数页进行软件回放')


def stages_from_archive(records,report,saved_uv):
 if report.get('version')!=VERSION:
  raise ValueError('此帧不是当前 near20 策略，不能套用新版流程；请在参数页使用历史回放')
 raw=[dict(r) for r in records]
 if len({r['_id'] for r in raw})!=len(raw):raise ValueError('候选编号重复')
 coords=lambda rows:np.asarray([[r['x'],r['y']] for r in rows],float).reshape(-1,2)
 stages=[]
 def add(name,explanation,rows):
  stages.append(dict(name=name,explanation=explanation,count=len(rows),uv=coords(rows).tolist()))
 add('FPGA 条纹候选','使用扫描时保存的候选中心、宽度、信号与 RGB 阈值',raw)
 ground=[r for r in raw if r['height_mm'] is not None and r['final_reason']!='第一步：转盘高度剔除']
 add('先去转盘','有限交点 → 按标定的转盘高度剔除；先于条纹竞争',ground)
 spatial=[r for r in ground if r['final_reason']!='第二步：几何深度/半径剔除']
 add('几何深度 / 半径','保留有效深度和扫描半径内候选',spatial)
 main,_,_=select_branch(spatial,False)
 extra,_,_=select_branch(spatial,True)
 occupied={r['y'] for r in main}
 chosen=sorted(main+[r for r in extra if r['y'] not in occupied],key=lambda r:r['y'])
 ids={r['_id'] for r in chosen}
 for r in raw:r['new_kept']=r['_id'] in ids
 add('双支路条纹筛选','两支路分别选峰、两次连续性及弱宽峰过滤；自适应只补主支路空行',chosen)
 secondary,_=secondary_decisions(raw)
 for r in raw:
  if r['_id'] in secondary:r['new_kept']=False
 chosen=[r for r in chosen if r['new_kept']]
 add('弱宽次峰剔除','稳定主线与重复侧支联合判定',chosen)
 near,_=near_decisions(raw)
 for r in raw:
  if r['_id'] in near:r['new_kept']=False
 chosen=[r for r in chosen if r['new_kept']]
 add('近峰筛选','间距 <20 px、弱/强 ≤60%，且强峰轨迹稳定才删除弱峰',chosen)
 add('长轨迹仅提示','只标记可疑点，不删除，不影响邻行支持',chosen)
 result=coords(chosen)
 expected={r['_id'] for r in records if r['new_kept']}
 if {r['_id'] for r in chosen}!=expected or result.shape!=saved_uv.shape or not np.allclose(result,saved_uv,atol=1e-7,rtol=0):
  raise ValueError('逐步筛选与存档点云不一致，已停止展示；未修改扫描结果')
 checks={'candidates':len(raw),'after_ground':len(ground),'after_geometry':len(spatial),'secondary_removed':len(secondary),'near_peak_removed':len(near),'retained_points':len(chosen)}
 if any(report.get(k)!=v for k,v in checks.items()) or report.get('long_track_deleted')!=0:
  raise ValueError('阶段统计与存档报告不一致，已停止展示')
 stages.append(dict(name='最终实测点云',explanation='最终点已与本帧扫描存档逐点核对通过',count=len(saved_uv),uv=saved_uv.tolist()))
 return stages


def run(folder):
 start=time.monotonic();req=read(folder/'request.json');root=job(req['run'])
 pos=root/f'position-{req["index"]:03d}';laser=req['laser'];source=pos/laser
 report=read(source/'strategy.json');records=read(source/'strategy-candidates.json',None)
 if not isinstance(records,list):raise ValueError('此帧未保存生产候选，无法展示真实逐步流程')
 header=read(source/'frame.json');roi=header['geometry']['roi_xyxy'];left,top,right,bottom=roi
 with np.load(source/'points.npz',allow_pickle=False) as saved:
  uv=saved['uv'].copy();xyz=saved['axis_frame_mm'].copy()
 steps=stages_from_archive(records,report,uv)
 def image(role):
  for ext in ('png','ppm'):
   p=pos/role/('same-frame.'+ext)
   if p.is_file():
    im=cv2.imread(str(p))
    if im is not None:return cv2.rotate(im,cv2.ROTATE_90_CLOCKWISE)
  raise ValueError('此角度未保留原图，无法生成亮度剖面')
 off,on=image('OFF'),image(laser);profiles=[];row_audit={};rows={}
 for r in records:rows.setdefault(r['y'],[]).append(r)
 for y in range(top,bottom):
  sig=np.maximum(on[y].astype(np.int16)-off[y].astype(np.int16),0).max(1).astype(np.uint16)
  pad=np.pad(sig,(2,2),mode='reflect');smooth=sum(w*pad[i:i+len(sig)] for i,w in enumerate((1,4,6,4,1)))/16
  profiles.append(np.stack([on[y].max(1)[left:right],off[y].max(1)[left:right],sig[left:right],smooth[left:right]]).astype(np.float32))
  detail=[dict(r,rid=r['_id'],retained=r['new_kept'],decision=r['final_reason'],axis_y_mm=r['height_mm'],prominence=None) for r in rows.get(y,[])]
  row_audit[y]=dict(y=y,production=True,baseline=None,records=detail,final_uv=[p for p in steps[-1]['uv'] if int(p[1])==y])
 np.savez_compressed(folder/'row-profiles.npz',profiles=np.stack(profiles))
 (folder/'row-audit.json').write_text(json.dumps(row_audit,ensure_ascii=False),encoding='utf-8')
 result=dict(pipeline_mode='production',pipeline_label='新版流程 · 存档点云核对通过',status='complete',request=req,roi=roi,steps=steps,xyz=xyz.tolist(),final_count=len(uv),ground=report['turntable_filter'],spatial_filter=report['spatial_filter'],row_profiles_available=True,seconds=time.monotonic()-start,execution='生产候选只读回放；最终二维点逐点核对存档，三维点直接读取存档',baseline_comparison=dict(uv_equal=True,count_equal=True),version=VERSION)
 (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
