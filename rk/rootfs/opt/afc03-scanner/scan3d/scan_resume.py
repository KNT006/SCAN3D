"""Explicit continuation plan: never repeat a movement whose count already advanced."""
import json
from pathlib import Path
import numpy as np

def plan_resume(output,state,motor,boot):
    if state.get('mode')!='scan3d' or state.get('status') not in ('paused','interrupted'):
        raise ValueError('只有暂停的整圈扫描可以继续')
    if state.get('boot_id')!=boot:raise ValueError('板卡已重启，无法确认原扫描角度')
    origin=state.get('initial_motor',{})
    if not origin or motor.get('session')!=origin.get('session') or motor.get('count_known')!=1 or motor.get('moving') or motor.get('pending'):
        raise ValueError('电机会话或位置状态不可靠，不能继续')
    final=state.get('final_motor',{})
    if not final or final.get('count_known')!=1 or motor.get('emitted')!=final.get('emitted') or motor.get('session')!=final.get('session'):
        raise ValueError('暂停后电机计数已变化，不能继续')
    n=state['planned_intervals'];schedule=[round(i*3200/n) for i in range(n+1)]
    saved=[];sizes=[];counts={'A':0,'B':0};gap=False
    for i in range(n+1):
        folder=Path(output)/f'position-{i:03d}'
        try:r=json.loads((folder/'status.json').read_text())
        except (OSError,ValueError):r={}
        complete=r.get('status')=='complete'
        if not complete:gap=True;continue
        if gap:raise ValueError('存档位置存在中间缺口，不能顺序续扫')
        for label in ('A','B'):
            h=json.loads((folder/label/'frame.json').read_text())
            if h['angle']['emitted_after']!=origin['emitted']+schedule[i]:raise ValueError('已存位置角度不匹配')
            with np.load(folder/label/'points.npz',allow_pickle=False) as a:
                xyz=a['axis_frame_mm'];rgb=a['rgb']
                if len(xyz)!=len(rgb) or not np.isfinite(xyz).all():raise ValueError('已存点云损坏')
                counts[label]+=len(xyz)
        saved.append(i);sizes.append(sum(f.stat().st_size for f in folder.rglob('*') if f.is_file()))
    start=len(saved)
    if not start:raise ValueError('起始采集尚未完成，请新建扫描')
    previous=origin['emitted']+schedule[start-1]
    target=origin['emitted']+schedule[start] if start<=n else previous
    if not previous<=motor['emitted']<=target:raise ValueError('当前计数不在中断前后位置，拒绝重放移动')
    return dict(start=start,origin=origin['emitted'],session=origin['session'],skip_move=motor['emitted']==target,current=motor['emitted'],counts=counts,sizes=sizes)
