"""Read-only archive replay through the live RK selector; never touches hardware.

Image curves explain saved candidates; they are not a second extraction algorithm.
"""
import sys,json,time,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scan3d'),str(ROOT/'fpga')]
import cv2
import numpy as np
from common import read,job,DATA
from row_results import FrameReceiver,require,MAX_PAYLOAD
from rgb_adaptive_strategy import validate_profile,color_thresholds,HASHES,SETTINGS
from rk_candidate_policy import select_candidates,VERSION
from pointcloud_adapter import PointCloudAdapter
from dual_identity import geometry_candidates
from turntable_filter import load_filter
from spatial_filter import validate as validate_spatial


def load_archive(folder,laser):
    h=read(folder/'hardware-frame.json'); saved_header=read(folder/'frame.json')
    require(h.get('complete') is True and h.get('error')==0,'缺少已完成的 FPGA 原始帧头；不能用旧软件找峰冒充当前回放')
    validate_profile(h)
    require(h['laser_id']==laser,'存档激光身份不匹配')
    for key in ('stream_epoch','request_id','source_frame_id','background_generation','laser_id','laser_control','angle','geometry','calibration'):
        require(saved_header.get(key)==h[key],'软硬件帧头不一致: '+key)
    require(saved_header.get('complete') is True and saved_header.get('error')==0,'RK 存档不是完整帧')
    binary=folder/'records.bin'
    require(binary.is_file() and 0<binary.stat().st_size<=MAX_PAYLOAD and binary.stat().st_size%16==0,'FPGA 候选记录缺失、越界或截断')
    payload=binary.read_bytes()
    context={k:h[k] for k in ('stream_epoch','background_generation','geometry','laser_id','laser_control','calibration','algorithm')}
    receiver=FrameReceiver(context,clock=lambda:0)
    receiver.register(h['request_id'],h['angle'],h['source_frame_id']); receiver.begin(dict(h,complete=False))
    for offset in range(0,len(payload),16):receiver.push(payload[offset:offset+16])
    # Archives lack the independent hardware footer CRC: this permits protocol
    # parsing, but is NOT evidence of the original transport's CRC integrity.
    footer=dict(stream_epoch=h['stream_epoch'],request_id=h['request_id'],source_frame_id=h['source_frame_id'],complete=True,error=0,
        row_count=h['geometry']['roi_xyxy'][3]-h['geometry']['roi_xyxy'][1],center_count=len(receiver.staged['centers']),record_count=len(payload)//16,payload_crc32=zlib.crc32(payload))
    frame=receiver.finish(footer)
    raw=[dict(x=c.num/c.den,y=c.row,k=c.peak_x,peak32=c.strength,lo=c.lo,hi=c.hi,width=c.hi-c.lo+1,signalmax=c.peak32&255,saturated=(c.peak32>>8)&1) for c in frame.centers]
    saved=read(folder/'strategy-candidates.json')
    if isinstance(saved,list):
        require(len(saved)==len(raw),'候选 JSON 与二进制数量不符')
        for r,s in zip(raw,saved):require(all(r[k]==s.get(k) for k in r),'候选 JSON 与二进制字段不符')
    else:saved=None
    return h,saved_header,raw,saved


def image(position,role):
    for ext in ('png','ppm'):
        path=position/role/('same-frame.'+ext)
        if path.is_file():
            im=cv2.imread(str(path))
            require(im is not None and im.shape==(1080,1920,3),'原图无法读取或尺寸错误: '+role)
            return cv2.cvtColor(cv2.rotate(im,cv2.ROTATE_90_CLOCKWISE),cv2.COLOR_BGR2RGB)
    return None


def archived_colors(raw,saved):
    """Apply the deployed mapping to saved local RGB statistics, not old decisions."""
    require(saved is not None,'缺少同角度 COLOR 原图和候选局部 RGB 记录，无法忠实回放')
    for r,s in zip(raw,saved):
        rgb=np.asarray(s.get('rgb'),float); spread=s.get('color_spread')
        require(rgb.shape==(3,) and np.isfinite(rgb).all() and ((rgb>=0)&(rgb<=255)).all(),'存档局部 RGB 无效')
        require(isinstance(spread,(int,float)) and np.isfinite(spread) and spread>=0,'存档颜色离散度无效')
        v=float(rgb.max()); reliable=12<=v<245 and spread<=35
        suggested=int(np.floor(25+15*np.clip((v-100)/60,0,1)+.5))
        r.update(rgb=rgb.tolist(),v=v,color_spread=spread,color_reliable=bool(reliable),color_threshold=suggested,threshold=suggested if reliable else 40)


def current_adapter(root):
    adapter=PointCloudAdapter(root/'bundle',geometry_candidates)
    require(adapter.hashes==HASHES,'历史标定不兼容当前 FPGA 空间 ROM')
    adapter.turntable_filter=load_filter(ROOT/'fpga/new-strategy-bundle',adapter.hashes)
    require(adapter.turntable_filter is not None,'当前转盘配置缺失，不能静默跳过去转盘')
    path=DATA/'scan3d-work/spatial-profile.json'
    require(path.is_file(),'当前空间配置缺失；请恢复已部署的 spatial-profile.json')
    adapter.spatial_filter=validate_spatial(read(path))
    require(adapter.spatial_filter.get('axis_sha256',adapter.hashes['axis_sha256'])==adapter.hashes['axis_sha256'],'空间配置标定不匹配')
    return adapter


def run(folder,root=None,adapter=None):
    start=time.monotonic(); folder=Path(folder); req=read(folder/'request.json')
    require(req.get('mode','current_scan')=='current_scan','仅支持当前实际扫描策略回放')
    require(not req.get('parameters') and not req.get('spatial'),'当前策略回放不接受旧试验参数；请刷新页面')
    root=Path(root) if root is not None else job(req['run'])
    pos=root/f'position-{req["index"]:03d}'; laser=req['laser']
    require(laser in ('A','B'),'激光必须是 A 或 B')
    h,old_header,raw,saved=load_archive(pos/laser,laser)
    adapter=adapter or current_adapter(root)
    require(adapter.hashes==HASHES,'标定哈希不匹配')
    cfg=adapter.spatial_filter
    require(cfg['enabled'] and float(cfg['radius_mm'])==70 and float(cfg.get('margin_mm',0))==0,'当前 ABI6 回放要求空间半径 70 mm、余量 0')
    color=image(pos,'COLOR')
    if color is not None:
        for r,t in zip(raw,color_thresholds(color,raw)):r.update(t)
        color_source='same_angle_raw_COLOR'
    else:archived_colors(raw,saved); color_source='archived_candidate_local_RGB'
    trace={}; header=dict(h,algorithm=VERSION,protocol='afc03.rk-stripes.v1')
    arrays,report,records=select_candidates(raw,header,adapter,trace=trace)
    coords=lambda ids:[[records[i]['x'],records[i]['y']] for i in ids]
    stages=[]
    def stage(key,name,explanation,ids,**extra):
        stages.append(dict(key=key,name=name,explanation=explanation,count=len(ids),uv=coords(ids),**extra))
    stage('validated','FPGA 候选校验','读取 FPGA 亮核候选，校验帧号、身份、行完成和元数据；FPGA 未输出的早期拒绝峰不在存档内。',list(range(len(records))))
    stage('finite','有限交点','计算标定射线交点以判断高度；无有限交点先剔除。',trace['finite'])
    stage('ground','先去转盘',f"转盘轴 Y > {adapter.turntable_filter['min_axis_y_mm']} mm。",trace['ground'])
    stage('geometry','几何空间筛选','相机深度 80 < Z < 350 mm，转轴半径 ≤ 70 mm。',trace['geometry'])
    for key,name,explanation in [
        ('threshold','差分 / 局部 RGB','固定 40 主支路与局部 7×7 RGB 支路分别处理；自适应弱于 40 时宽度 ≤ 25。'),
        ('top2','每行候选整理','各支路内峰距 ≥ 8、窗口不重叠，每行最多两候选；不是旧多峰亮度方案二。'),
        ('continuity1','第一次连续性','前后各 4 行，至少 3 行支持，横向距离 ≤ 2+3×行距。'),
        ('weak_width','弱亮宽峰限制','差分 < 80 时亮区宽度 ≤ 65。'),
        ('continuity2','第二次连续性','在上一步剩余候选中复核邻行支持。'),
        ('spatial_support','有效邻行支持','各支路使用有效候选检查空间内邻行支持。'),
        ('retained','自适应弱峰支持','自适应支路差分 < 40 时至少 4 行支持。')]:
        main=trace['main'][key]; extra=trace['adaptive'][key]
        stage(key,name,explanation+' 图示两支路并集，尚未补行合并。',sorted(set(main)|set(extra)),main_count=len(main),adaptive_count=len(extra),parallel_branches=True)
    stage('merged','主支路优先合并','只有固定 40 主支路整行无点时，才加入自适应支路该行。',trace['merged'])
    stage('secondary','弱宽次候选检查','使用候选宽度、相对亮度、稳定主线与重复侧支联合检查；不虚构未保存的局部突出度。',trace['after_secondary'])
    stage('near20','近峰 20 / 60%','距离 < 20 px、弱/强 ≤ 0.60 且强峰邻行轨迹稳定时只删弱峰。',trace['final'])
    stage('final','最终点 · 长轨迹仅标记',f"长轨迹嫌疑 {len(trace['suspects'])} 点，只标记、不删除。旧多峰判定及分支恢复关闭。",trace['final'],suspect_uv=coords(trace['suspects']))
    on,off=image(pos,laser),image(pos,'OFF'); profiles=None
    left,top,right,bottom=h['geometry']['roi_xyxy']
    if on is not None and off is not None:
        signal=np.maximum(on.astype(np.int16)-off.astype(np.int16),0).max(2).astype(np.float32)
        patch=signal[top:bottom]; padded=np.pad(patch,((0,0),(2,2)),mode='reflect')
        smooth=sum(w*padded[:,i:i+1080] for i,w in enumerate((1,4,6,4,1)))/16
        profiles=np.stack([on[top:bottom].max(2),off[top:bottom].max(2),patch,smooth],axis=1)[:,:,left:right]
        np.savez_compressed(folder/'row-profiles.npz',profiles=profiles)
    rows={str(y):dict(y=y,records=[],final_uv=[],baseline=None) for y in range(top,bottom)}
    membership={s['key']:set(map(tuple,s['uv'])) for s in stages}
    for r in records:
        i=r['_id']; branches={}
        for label in ('main','adaptive'):
            branches[label]=dict(reason=trace[label]['reasons'].get(i,'未进入支路'),passed_stages=[k for k,ids in trace[label].items() if k!='reasons' and i in ids])
        r.update(rid=i,retained=r['new_kept'],decision=r['final_reason'],axis_y_mm=r['height_mm'],branches=branches,
                 adaptive_origin=i in trace['adaptive_added'],effective_threshold=r['threshold'] if i in trace['adaptive_added'] else 40,
                 passed_stages=[k for k,uv in membership.items() if (r['x'],r['y']) in uv])
        rows[str(r['y'])]['records'].append(r)
    for x,y in arrays['uv']:rows[str(int(y))]['final_uv'].append([float(x),int(y)])
    comparison=None
    if (pos/laser/'points.npz').is_file():
        with np.load(pos/laser/'points.npz',allow_pickle=False) as original:
            uv=original['uv'];comparison=dict(saved_algorithm=old_header['algorithm'],saved_count=len(uv),current_count=len(arrays['uv']),uv_equal=bool(uv.shape==arrays['uv'].shape and np.allclose(uv,arrays['uv'],atol=1e-7,rtol=0)),comparison_scope='历史结果与当前策略对比；未覆盖原点云')
    result=dict(status='complete',replay_version='scan-flow-shared-v1',strategy_version=VERSION,request=req,roi=h['geometry']['roi_xyxy'],steps=stages,xyz=arrays['axis_frame_mm'].tolist(),final_count=len(arrays['uv']),report=report,
        ground=report['turntable_filter'],spatial_filter=report['spatial_filter'],stripe_settings=SETTINGS,row_profiles_available=profiles is not None,color_source=color_source,baseline_comparison=comparison,
        seconds=time.monotonic()-start,execution='RK 当前扫描策略 · 历史候选只读回放',archive_validation='已校验帧头、行完成、候选字段；未保存独立硬件 CRC，重算 CRC 不构成历史传输完整性证明',configuration_scope='历史几何标定 + 当前部署转盘/空间配置')
    (folder/'row-audit.json').write_text(json.dumps(rows,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    return result


if __name__=='__main__':
    cv2.setNumThreads(1)
    folder=Path(sys.argv[1])
    try:run(folder)
    except Exception as error:
        (folder/'result.json').write_text(json.dumps(dict(status='failed',error=str(error)),ensure_ascii=False),encoding='utf-8')
        raise
