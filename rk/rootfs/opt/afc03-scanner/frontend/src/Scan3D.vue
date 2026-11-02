<template>
<div class="scan3d">
 <header class="topbar"><div class="scan-brand"><img class="scan-brand-lockup" :src="scanBrandLogo" alt="SCAN3D 标志与 3DSCAN 字标" /></div><nav><button v-for="(t,i) in tabs" :class="{active:tab===i}" @click="tab=i"><span>0{{i+1}}</span>{{t}}</button></nav><span v-if="!online" class="connection-alert">设备未连接</span><button class="stop header-stop" @click="stop">■ 停止 / 关闭光源</button><div class="partner-logo"><img :src="anlogicLogo" alt="安路 Anlogic 手绘标志"/></div></header>
 <div v-if="message" class="toast" :class="{bad:failed}" role="status" @click="message=''">{{message}} <span>×</span></div>
 <main :class="{'museum-main':tab===4}">
 <div v-if="tab!==4" class="workspace-heading"><div><span class="page-index">0{{tab+1}} / SCAN3D</span><h1>{{tabs[tab]}}</h1></div><WorkbenchSketch :kind="tab===2?'results':'scanner'"/></div>
 <template v-if="tab===0">
 
 <div class="params-layout" style="flex:1;height:auto">
  <section class="panel controls" :class="'control-group-'+group"><div class="panel-title"><h2>采集设置</h2></div><div class="segments parameter-groups"><button v-for="g in groups" :key="g.id" :class="{chosen:group===g.id}" @click="group=g.id">{{g.name}}</button></div>
   <div class="form-body" v-if="group===0"><label>扫描名称<input v-model="title" maxlength="80" placeholder="物品名称 / 批次"/></label><label>角度步长<select v-model.number="step"><option :value="6">6°　60 个位置 / 粗扫</option><option :value="2">2°　180 个位置</option><option :value=".45">0.45°　800 个位置</option><option :value=".1125">0.1125°　3200 个位置</option></select></label><label class="checkbox"><input type="checkbox" v-model="ready"/>物体固定、支架未动、挡板打开，驱动已供电</label><button class="primary wide" :disabled="locked||!ready" @click="startScan">开始整圈扫描</button></div>
   <div class="form-body light-motor-form" v-else-if="group===1"><label>灯带亮度 <b>{{led}} / 32</b><input type="range" v-model.number="led" min="0" max="32"/></label><button class="primary" :disabled="lightsLocked" @click="control({op:'lights',led})">补光灯开</button><button :disabled="lightsLocked" @click="control({op:'lights',led:0})">补光灯关</button><label>激光通道</label><div class="button-grid"><button :class="{chosen:laserChannel.includes('A')}" :aria-pressed="laserChannel.includes('A')" :disabled="lightsLocked" @click="control({op:'lights',laser_a:!laserChannel.includes('A')})">激光 A {{laserChannel.includes('A')?'关':'开'}}</button><button :class="{chosen:laserChannel.includes('B')}" :aria-pressed="laserChannel.includes('B')" :disabled="lightsLocked" @click="control({op:'lights',laser_b:!laserChannel.includes('B')})">激光 B {{laserChannel.includes('B')?'关':'开'}}</button><button :disabled="lightsLocked" @click="control({op:'lights',laser:'AB'})">双激光开</button><button :disabled="lightsLocked" @click="control({op:'lights',laser:'OFF'})">双激光关</button></div><MotorDial :disabled="!!locked" @turn="control({op:'move',angle:$event,rate:40})" @stop="stop"/><button :disabled="locked" @click="control({op:'recover_manual_motion',ready:true})">恢复手动转动</button><small>中途停止后，先恢复再选择角度转动。恢复会以当前位置重置计数，旧扫描不能据此精确续扫。</small></div>
   <div class="form-body stripe-form" v-else-if="group===3"><div class="field-grid"><label v-for="k in paramGroups.flat()">{{labels[k]}}<input type="number" :value="policy.settings?.[k]" readonly/></label></div><div class="policy-note">局部 RGB 亮度 100–160 → 阈值 25–40；固定 40 主支路优先。近峰 &lt;20 px、弱/强 ≤60% 且强峰轨迹稳定才删弱峰。长轨迹只标记；旧多峰判定与分支恢复关闭。</div><button class="primary" :disabled="replaying||historyLocked||!replayPositions.includes(index)" @click="replay">{{replaying?'处理中…':'按当前策略回放此帧'}}</button><label class="checkbox"><input type="checkbox" v-model="autoReplay"/>切换帧后自动回放</label></div>
   
  </section>
  <template v-if="true">
  <section class="panel source-panel"><div class="panel-title"><h2>当前帧与最终条纹点</h2></div><div class="frame-toolbar"><select class="frame-run-select" v-model="selected" @change="selectRun"><option v-for="r in runs" :value="r.id">{{r.title}}　{{r.id}}</option></select><FrameStepper v-model="index" :positions="replayPositions"/><select class="frame-laser-select" v-model="laser"><option>A</option><option>B</option></select><button :disabled="replaying||historyLocked||!replayPositions.includes(index)" @click="replay">分析帧</button></div><p v-if="historyReplayHint" class="policy-note" role="status">{{historyReplayHint}}</p><div class="frame-area"><svg v-if="selected" viewBox="0 0 1080 1920"><image v-if="!frameImageError" @error="frameImageError=true" :href="imageUrl" width="1920" height="1080" transform="translate(1080 0) rotate(90)"/><rect v-if="audit" :x="audit.roi[0]" :y="audit.roi[1]" :width="audit.roi[2]-audit.roi[0]" :height="audit.roi[3]-audit.roi[1]" fill="none" stroke="#62dbc2" stroke-width="2"/><circle v-for="(p,i) in finalUV" :key="i" :cx="p[0]" :cy="p[1]" r="2.8" fill="#ffbd64"/></svg><div v-else class="empty"><template v-if="frameImageError">此帧原图暂不可用<button @click="retryFrameImage">重新加载</button></template><template v-else>选择已有扫描或抓取 A/B 帧</template></div></div><div class="panel-foot"><button :disabled="locked" @click="capture">抓取新的 A/B 帧</button></div></section>
  <div class="parameter-preview-stack"><section class="panel parameter-camera"><div class="panel-title"><h2>实时相机预览</h2></div><div class="camera-box"><CameraPreview :stream-id="camera?.stream_id"><svg v-if="state?.scan_roi" viewBox="0 0 1080 1920" aria-label="当前扫描取景范围"><rect :x="state.scan_roi[0]" :y="state.scan_roi[1]" :width="state.scan_roi[2]-state.scan_roi[0]" :height="state.scan_roi[3]-state.scan_roi[1]" fill="none" stroke="#62dbc2" stroke-width="3"/></svg></CameraPreview></div><div class="panel-foot">原始取景</div></section></div>
 </template>
 </div></template>
 <template v-else-if="tab===1">
 <div class="monitor-head"><span>{{monitorLabel}}　{{monitorId||'尚未提交任务'}}</span></div>
 <div v-if="monitorFailure||monitorError" class="monitor-alert" role="alert"><b>{{monitorError||monitorFailure}}</b><small v-if="monitorState.initial_capture?.color">有效点对应像素的亮度中位数 {{monitorState.initial_capture.color.median_max}}（当前要求 60＜亮度＜245）；过曝比例 {{(monitorState.initial_capture.color.saturated_fraction*100).toFixed(1)}}%。深色表面也可能触发，不能据此判定灯光故障；已显示的点仅为起始位置预览。</small><small v-if="monitorState.error">{{errorZh(monitorState.error)}}</small></div>
 <div v-if="['paused','interrupted'].includes(monitorState.status)" class="monitor-alert"><label class="checkbox"><input type="checkbox" v-model="resumeReady"/>暂停后物品、相机与转盘未移动，驱动保持供电</label><button class="primary" :disabled="locked||!resumeReady||!monitorId" @click="resumeScan(monitorId)">继续本次扫描</button></div>
 <div class="monitor-grid"><ColorPairPreview :stream-id="camera?.stream_id" :roi="state?.scan_roi"/><section class="panel"><div class="panel-title"><h2>03 / 增量点云</h2></div><ScanScene :preview="monitorPreview" :preview-revision="monitorRevision"/></section></div>
 <div class="metric-strip"><div><small>本任务预览点</small><b>{{monitorPreview.count.toLocaleString()}}</b></div><div><small>通过检查的位置 / 计划</small><b>{{monitorState.completed_positions??0}} / {{monitorState.planned_intervals!==undefined?monitorState.planned_intervals+1:'—'}}</b></div><div><small>本任务实际耗时</small><b>{{fmt(monitorState.elapsed_seconds)}} s</b></div><div><small>采集重试</small><b>{{monitorState.capture_retries??0}}</b></div><div><small>任务状态</small><b class="monitor-status">{{monitorLabel}}</b></div></div>
 </template>
 <template v-else-if="tab===2"><div class="results-layout"><section class="panel"><div class="panel-title"><h2>扫描档案</h2></div><div class="run-list"><button v-for="r in pagedRuns" :class="{chosen:selected===r.id}" @click="selected=r.id;selectRun()"><b>{{r.title}}</b><small>{{r.id}}</small><span>{{r.passed?'完成':r.supplemental_closure?'补拍复核通过':({paused:'已暂停',failed:'失败',running:'运行中',interrupted:'已中断'} as any)[r.state]||r.state}}　{{fmt(r.elapsed)}} s</span></button></div><div class="pagination"><button :disabled="page===0" @click="page--">上一页</button><span>{{page+1}} / {{Math.max(1,Math.ceil(runs.length/5))}}</span><button :disabled="(page+1)*5>=runs.length" @click="page++">下一页</button></div></section><section class="panel"><div class="panel-title"><h2>{{resultMode==='points'?'彩色点云':'STL 网格'}}</h2><div class="segments"><button :class="{chosen:resultMode==='points'}" @click="resultMode='points'">点云</button><button :class="{chosen:resultMode==='stl'}" @click="resultMode='stl'">STL</button></div></div><ScanScene v-if="resultMode==='points'" :key="selected" :binary="aiPreview||resultCloud" :loading="cloudLoading" :load-error="cloudError" :waiting="active===selected?'扫描进行中，请在实时监控查看；结束后显示完整点云':''"/><MeshTasks v-else :run="selected" :run-title="runs.find(r=>r.id===selected)?.title" :locked="!!active" @imported="museumExhibit=$event;tab=4"/><div class="panel-foot"><span>{{resultMode==='points'?(aiPreviewId?'AI 过滤审阅点云':'实测点云'):'重建曲面'}}</span><button v-if="cloudError&&resultMode==='points'" @click="retryCloud">重新加载</button></div></section><section class="panel report-panel"><div class="panel-title"><h2>质量与报告</h2></div><div class="report-body"><div class="report-hero"><small>本次扫描总耗时</small><div class="big-number">{{fmt(details?.state?.elapsed_seconds)}}<em>s</em></div></div><dl><div><dt>实测点数</dt><dd>{{details?.count?.toLocaleString()||'—'}}</dd></div><div><dt>角度步长</dt><dd>{{details?.state?.requested_step_deg??'—'}}°</dd></div><div><dt>包围盒 X / Y / Z</dt><dd>{{details?.bounds_mm?.join(' / ')||'—'}} mm</dd></div><div><dt>测量精度</dt><dd class="warn">未经独立标定验证</dd></div><div><dt>首尾检查</dt><dd>{{details?.state?.closure?.passed?'通过':details?.supplemental_closure?'原图偏暗；补拍复核通过':details?.state?.closure?'原始检查未通过':'暂无记录'}}</dd></div></dl><div v-if="['paused','interrupted'].includes(details?.state?.status)"><label class="checkbox"><input type="checkbox" v-model="resumeReady"/>物品、相机和转盘未移动，驱动保持供电</label><button class="primary wide" :disabled="locked||!resumeReady" @click="resumeScan(selected)">继续所选扫描</button></div><div class="report-links"><a v-for="f in details?.reports||[]" :href="`/api/scan3d/runs/${selected}/report/${f}`" target="_blank">{{reportName(f)}} ↗</a></div><AiCloudFilter :run="selected" :locked="!!active||replaying||!online" @preview="previewAi"/><button class="secondary wide" :disabled="historyLocked||replaying||!selected||!online" @click="openRename">重命名模型</button><button class="secondary wide" :disabled="!!active||!selected||busy" @click="archive">导出模型与报告归档</button><button class="danger-outline wide" :disabled="historyLocked||cleanupWorking||!selected" @click="openCleanup">清理 / 删除所选扫描</button></div></section></div></template>
 <template v-else-if="tab===3"><div class="flow-head"><div class="frame-toolbar"><select class="frame-run-select" v-model="selected" @change="selectRun"><option v-for="r in runs" :value="r.id">{{r.title}}　{{r.id}}</option></select><FrameStepper v-model="index" :positions="replayPositions"/><select class="frame-laser-select" v-model="laser"><option>A</option><option>B</option></select><button class="primary" :disabled="replaying||historyLocked||!replayPositions.includes(index)" @click="replay">{{replaying?'计算中…':'分析此帧'}}</button></div><p v-if="historyReplayHint" class="policy-note" role="status">{{historyReplayHint}}</p></div><div class="flow-layout"><section class="panel steps"><button v-for="(s,i) in audit?.steps||[]" :class="{chosen:stage===i}" @click="stage=i"><span>{{String(i+1).padStart(2,'0')}}</span><div><b>{{stepLabel(s.name)}}</b><small>{{s.count}} 个候选 / 点<span v-if="s.parallel_branches"> · 主 {{s.main_count}} / 自适应 {{s.adaptive_count}}</span></small></div></button><p v-if="!audit" class="empty">{{details&&!replayPositions.length?'此扫描没有保留完整原图，无法逐帧对照分析':'选择帧后点击“分析此帧”'}}</p></section><section class="panel"><div class="panel-title"><h2>{{stepLabel(audit?.steps?.[stage]?.name)||'条纹逐步回放'}}</h2></div><div class="frame-area"><svg v-if="selected" viewBox="0 0 1080 1920" @click="pickRow" style="cursor:crosshair"><image v-if="!frameImageError" @error="frameImageError=true" :href="imageUrl" width="1920" height="1080" transform="translate(1080 0) rotate(90)"/><text v-if="frameImageError" x="170" y="970" fill="#ddd" font-size="22">原图未保留，仅显示候选坐标</text><circle v-for="(p,i) in audit?.steps?.[stage]?.uv||[]" :key="i" :cx="p[0]" :cy="p[1]" r="2.7" fill="#ffbd64"/><circle v-for="(p,i) in audit?.steps?.[stage]?.suspect_uv||[]" :key="'suspect'+i" :cx="p[0]" :cy="p[1]" r="5" fill="none" stroke="#ffd344" stroke-width="2"/><line v-if="audit" :x1="audit.roi[0]" :x2="audit.roi[2]" :y1="profileRow" :y2="profileRow" stroke="#f0d441" stroke-width="2" stroke-dasharray="8 5"/><text v-if="audit" :x="audit.roi[0]" :y="profileRow-10" fill="#fff" font-size="22">y={{profileRow}}</text></svg><div v-else-if="frameImageError" class="empty">此帧原图暂不可用<button @click="retryFrameImage">重新加载</button></div></div><div class="panel-foot flow-explanation">{{audit?.steps?.[stage]?.explanation||'选择历史帧，按当前扫描策略重算'}}</div></section><section class="panel flow-detail"><div class="panel-title"><h2>逐行判定依据</h2><div class="segments"><button :class="{chosen:flowView==='row'}" @click="flowView='row'">亮度剖面</button><button :class="{chosen:flowView==='cloud'}" @click="flowView='cloud'">三维结果</button></div></div><RowProfile v-if="flowView==='row'" :audit="audit" v-model:row="profileRow"/><ScanScene v-else :points="audit?.xyz||[]"/><div class="panel-foot"><span>实际扫描策略 · 长轨迹不删点</span><button @click="tab=0;group=3">查看参数</button></div></section></div></template>
 <MuseumWorkspace v-else-if="tab===4" :exhibit="museumExhibit"/>
 <SettingsPanel v-else :online="online" :state="state" :camera="camera" :device="device"/>
 </main>
 <div v-if="renameOpen" class="cleanup-backdrop" @keydown.esc="!renameWorking&&(renameOpen=false)">
  <section class="cleanup-dialog" role="dialog" aria-modal="true" aria-labelledby="rename-title">
   <div class="panel-title"><h2 id="rename-title">重命名模型</h2><button :disabled="renameWorking" @click="renameOpen=false" aria-label="关闭重命名窗口">×</button></div>
   <form class="cleanup-body" @submit.prevent="saveRename">
    <label>模型名称<input ref="renameInput" v-model="renameTitle" maxlength="80" :disabled="renameWorking" required aria-label="模型名称"/></label>
    <p v-if="renameError" class="cleanup-error" role="alert">{{renameError}}</p>
    <div class="cleanup-actions"><button type="button" :disabled="renameWorking" @click="renameOpen=false">取消</button><button class="secondary" :disabled="renameWorking||!renameTitle.trim()">{{renameWorking?'正在保存…':'保存名称'}}</button></div>
   </form>
  </section>
 </div>
 <div v-if="cleanupOpen" class="cleanup-backdrop" @keydown.esc="closeCleanup">
  <section class="cleanup-dialog" role="dialog" aria-modal="true" aria-labelledby="cleanup-title">
   <div class="panel-title"><h2 id="cleanup-title">{{cleanupStage===1?'确认永久删除':'清理扫描数据'}}</h2><button :disabled="cleanupWorking" @click="closeCleanup" aria-label="关闭清理窗口">×</button></div>
   <div class="cleanup-body">
    <p class="cleanup-id">所选扫描 <b>{{cleanupName}}</b></p>
    <div v-if="cleanupStage===0" class="button-grid"><button :class="{chosen:cleanupMode==='photos'}" :disabled="cleanupWorking" @click="setCleanupMode('photos')">仅删除原始照片</button><button :class="{chosen:cleanupMode==='all'}" :disabled="cleanupWorking" @click="setCleanupMode('all')">删除整次扫描</button></div>
    <p class="hint warn">{{cleanupMode==='photos'?'删除采集原图后，不能再回放这些帧或重新提取条纹；保留已有点云、STL、标定与报告。':'删除所选扫描目录的全部数据，并删除同名已发布结果目录；历史派生模型若目录名不同则保留。'}}</p>
    <template v-if="cleanupPlan">
     <div class="cleanup-summary"><div><small>将删除文件</small><b>{{cleanupPlan.count.toLocaleString()}} 个</b></div><div><small>预计释放空间</small><b>{{sizeText(cleanupPlan.estimated_reclaim_bytes)}}</b></div></div>
     <p class="hint">{{cleanupPlan.scope}}</p>
     <div class="cleanup-paths"><small>涉及目录</small><div v-for="r in cleanupPlan.roots">{{r}}</div></div>
     <p class="hint">文件类型：{{Object.entries(cleanupPlan.types).map(([k,v])=>`${k} × ${v}`).join('　')||'无'}}<br>空间为估算；电脑、外置存储上的副本不受影响。归档导出不包含原始照片。</p>
    </template>
    <p v-else class="hint">{{cleanupWorking?'正在统计文件和空间…':'无法取得删除范围，请重试。'}}</p>
    <template v-if="cleanupStage===1"><label class="cleanup-ack"><input type="checkbox" v-model="cleanupAck" :disabled="cleanupWorking"/>我已确认范围，理解这是永久删除，无法在界面撤销。</label></template>
    <p v-if="cleanupError" class="cleanup-error" role="alert">{{cleanupError}}</p>
    <div class="cleanup-actions"><button :disabled="cleanupWorking" @click="closeCleanup">取消</button><button v-if="cleanupStage===0&&!cleanupPlan" :disabled="cleanupWorking" @click="previewCleanup">重新统计</button><button v-if="cleanupStage===0" class="stop" :disabled="cleanupWorking||!cleanupPlan?.count||cleanupTargetLocked" @click="cleanupStage=1">下一步：确认删除</button><template v-else><button :disabled="cleanupWorking" @click="cleanupStage=0">返回查看范围</button><button class="stop" :disabled="cleanupWorking||cleanupTargetLocked||!cleanupPlan?.count||!cleanupAck" @click="executeCleanup">{{cleanupWorking?'正在删除…':'永久删除'}}</button></template></div>
   </div>
  </section>
 </div>
 </div>
</template>
<script setup lang="ts">
import scanBrandLogo from './assets/scan3d-brand-sage.png'
import MuseumWorkspace from './MuseumWorkspace.vue'
import FrameStepper from './FrameStepper.vue'

import {errorZh} from './errorZh'
import {ref,shallowRef,computed,onMounted,onBeforeUnmount,watch,nextTick} from 'vue'
import {parseResultCloud,summarizeResultCloud,type ResultCloud} from './cloudBinary'
import {useScanMonitor,scanFailure} from './useScanMonitor'
import WorkbenchSketch from './WorkbenchSketch.vue';import MotorDial from './MotorDial.vue';
import AiCloudFilter from './AiCloudFilter.vue';
import RowProfile from './RowProfile.vue';import MeshTasks from './MeshTasks.vue';
import ColorPairPreview from './ColorPairPreview.vue';import CameraPreview from './CameraPreview.vue';import ScanScene from './ScanScene.vue';import './scan3d.css';import './minimal.css';import './paper-wood.css';import './frame-toolbar.css';import SettingsPanel from './SettingsPanel.vue';import anlogicLogo from './assets/anlogic-sketch.png'
const aiPreview=shallowRef<ResultCloud|null>(null),aiPreviewId=ref('')
let aiPreviewEpoch=0
async function previewAi(id:string){const epoch=++aiPreviewEpoch;aiPreview.value=null;aiPreviewId.value='';resultMode.value='points';if(!id)return;try{const r=await fetch(`/api/scan3d/ai-filter/${id}/files/cloud`);if(!r.ok)throw Error('AI 点云读取失败');const data=await r.arrayBuffer();if(epoch!==aiPreviewEpoch)return;aiPreview.value=parseResultCloud(data);aiPreviewId.value=id}catch(e:any){notify(e.message,true)}}
const frameImageError=ref(false),frameImageVersion=ref(0)
const profileRow=ref(1447),flowView=ref('row')
function pickRow(e:MouseEvent){if(!audit.value)return;const svg=e.currentTarget as SVGSVGElement;const pt=svg.createSVGPoint();pt.x=e.clientX;pt.y=e.clientY;const q=pt.matrixTransform(svg.getScreenCTM()!.inverse());profileRow.value=Math.max(audit.value.roi[1],Math.min(audit.value.roi[3]-1,Math.round(q.y)));flowView.value='row'}
const tabs=['参数调节','实时监控','扫描结果','条纹提取流程','物品陈列馆','设置'],groups=[{id:0,name:'扫描'},{id:1,name:'光源 / 电机'},{id:3,name:'条纹'}]
const museumExhibit=ref('')
const tab=ref(0),group=ref(0),state=ref<any>({}),camera=ref<any>({}),device=ref<any>({}),runs=ref<any[]>([]),details=ref<any>(),selected=ref(''),index=ref(0),laser=ref('A'),step=ref(6),title=ref('新物品'),ready=ref(false),led=ref(8),gain=ref(50),online=ref(false),busy=ref(false),message=ref(''),failed=ref(false),cameraInfo=ref(''),audit=ref<any>(),replaying=ref(false),autoReplay=ref(false),stage=ref(8),page=ref(0),resultMode=ref('points'),meshes=ref<any[]>([]),mesh=ref(''),params=ref<Record<string,number>>({})
watch(selected,()=>{aiPreviewEpoch++;aiPreview.value=null;aiPreviewId.value=''})
const resumeReady=ref(false)
const manualMoving=ref(false),lightsBusy=ref(false),stopping=ref(false)
const laserChannel=computed(()=>state.value.helper?.manual_laser?.channel||'OFF')
const lightsLocked=computed(()=>!online.value||busy.value||lightsBusy.value||stopping.value||!!active.value||state.value.helper?.worker_running||state.value.mesh_processing)
const spatial=ref({version:1,enabled:true,radius_mm:70,margin_mm:0})
async function saveSpatial(){try{const r=await api('/spatial-profile',spatial.value);spatial.value=r.profile;notify('空间范围已保存，后续扫描和静态采集生效；旧数据不改写')}catch(e:any){notify(e.message,true)}}
const monitor=useScanMonitor((path,signal)=>api(path,undefined,signal)),monitorId=monitor.id,monitorState=monitor.state,monitorPreview=monitor.preview,monitorRevision=monitor.revision,monitorError=computed(()=>monitor.error.value||monitor.stateError.value),monitorProgress=monitor.progress,monitorUpdate=monitor.lastUpdate
const monitorFailure=computed(()=>scanFailure(monitorState.value)),monitorLabel=computed(()=>({loading:'读取状态中',starting:'正在启动',running:'扫描中',complete:'已完成',paused:'已暂停',failed:'失败',interrupted:'已中断',stopping:'正在停止'} as any)[monitorState.value.status]||'等待扫描')
const active=computed(()=>state.value.active||(state.value.helper?.worker_running?state.value.helper.last_job:'')||''),live=computed(()=>state.value.scan||{}),locked=computed(()=>!online.value||manualMoving.value||state.value.helper?.manual_motion||lightsBusy.value||stopping.value||busy.value||!!active.value||state.value.helper?.worker_running||state.value.mesh_processing),imagePositions=computed<number[]>(()=>details.value?.image_positions??[]),imageUrl=computed(()=>`/api/scan3d/runs/${selected.value}/image/${index.value}/${laser.value}?v=${frameImageVersion.value}`),finalUV=computed(()=>audit.value?.steps?.at(-1)?.uv||[]),pagedRuns=computed(()=>runs.value.slice(page.value*5,page.value*5+5))
const historyLocked=computed(()=>busy.value||!!state.value.mesh_processing||!!selected.value&&selected.value===active.value)
const historyReplayHint=computed(()=>selected.value&&selected.value===active.value?'当前选择的是正在采集的扫描；请在上方选择其他已保存扫描。历史条纹分析可以与扫描同时进行。':'')
const policy=ref<any>({})
// Only navigate archived frames with OFF/A/B originals; candidate-only frames are not useful for visual review.
const replayPositions=computed<number[]>(()=>[...new Set(imagePositions.value)].filter(Number.isInteger).sort((a,b)=>a-b))
const labels:Record<string,string>={prominence:'峰突出度',distance:'候选最小峰距 / px',width_max:'亮区最大宽度',core_fraction:'亮核峰值比例',core_radius:'亮核半径 / px',signal_min:'主支路差分下限',weak_signal:'弱信号分界',weak_width_max:'弱信号最大宽度',neighbor_rows:'相邻行范围 ±',min_support:'最少支持行',dx_intercept:'横向容差截距',dx_per_row:'每行容差增量',adaptive_width:'自适应弱峰最大宽度',weak_support:'自适应弱峰支持行'}
// Presentation names only; archived algorithm versions and execution remain unchanged.
const stepLabel=(name:string='')=>name.replace(/^(?:FPGA|RK)\s+(?=条纹|候选|筛选)/,'')
const paramGroups=[['prominence','distance','width_max','core_fraction','core_radius'],['signal_min','weak_signal','weak_width_max','neighbor_rows','min_support','dx_intercept','dx_per_row','adaptive_width','weak_support']]
const fmt=(x:any)=>typeof x==='number'?x.toFixed(2):'—'
watch(replayPositions,(items)=>{if(items.length&&!items.includes(index.value))index.value=items[0]})
watch(imageUrl,()=>{frameImageError.value=false})
function retryFrameImage(){frameImageError.value=false;frameImageVersion.value++}
const reportName=(f:string)=>({'status.json':'扫描状态与原始记录','acceptance-audit.json':'数据完整性验收','timing-summary.json':'各流程耗时','delivery.json':'交付与补拍复核','review-model.json':'审阅模型说明'}[f]||f)
async function api(url:string,body?:any,signal?:AbortSignal){const r=await fetch('/api/scan3d'+url,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),...(signal?{signal}:{})}:{cache:'no-store',signal:signal?AbortSignal.any([signal,AbortSignal.timeout(8000)]):AbortSignal.timeout(8000)});const d=await r.json();if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:JSON.stringify(d.detail||d));return d}
let toastTimer:any
function notify(t:string,bad=false){message.value=bad?errorZh(t):t;failed.value=bad;clearTimeout(toastTimer);if(!bad)toastTimer=setTimeout(()=>message.value='',6000)}
async function control(d:any){
 if(d.op==='lights'?lightsLocked.value:locked.value)return
 const pending=d.op==='move'?manualMoving:d.op==='lights'?lightsBusy:busy;pending.value=true
 try{const r=await api('/control',d);if(r.manual_laser){pollEpoch++;state.value={...state.value,helper:{...state.value.helper,manual_laser:r.manual_laser}}}notify(r.message||r.readback||(r.actual_commanded_degrees!==undefined?`已完成指令转动 ${r.actual_commanded_degrees}°`:'命令已执行'));await poll();return r}
 catch(e:any){console.error(e);notify(e.message,true)}finally{pending.value=false}
}
async function stop(){if(stopping.value)return;stopping.value=true;try{await api('/control',{op:'stop'});notify('已发送停止和光源关闭命令');await poll()}catch(e:any){notify(e.message,true)}finally{stopping.value=false}}
async function startScan(){
 if(locked.value||!ready.value)return;
 busy.value=true;pollEpoch++
 try{const r=await api('/control',{op:'scan',step:step.value,title:title.value,ready:ready.value});pollEpoch++;monitor.bind(r.id,{status:'starting',elapsed_seconds:0,completed_positions:0,planned_intervals:Math.round(360/step.value)});selected.value=r.id;details.value=null;audit.value=null;index.value=0;resetCloud();state.value={...state.value,active:r.id};tab.value=1;notify('扫描已提交；先检查起始图像，再自动转动');await poll()}
 catch(e:any){notify(e.message,true)}finally{busy.value=false}
}
async function resumeScan(name:string){
 if(!resumeReady.value||busy.value)return
 busy.value=true
 try{const r=await api('/control',{op:'resume',name,ready:true});pollEpoch++;monitor.bind(r.id,{...(details.value?.state||monitorState.value),status:'starting'});tab.value=1;state.value={...state.value,active:r.id};resumeReady.value=false;notify('已提交续扫，正在核对存档与电机计数');await poll()}
 catch(e:any){notify(e.message,true)}finally{busy.value=false}
}
async function capture(){const r=await control({op:'capture',title:'静态调参帧',step:6});if(r){selected.value=r.id;details.value=null;index.value=0;audit.value=null;resetCloud();notify('已开始静态 A/B/颜色采集，转盘不动；完成后点击分析帧')}}
async function saveProfile(){try{await api('/profile',params.value);notify('候选参数已保存；正式扫描仍使用已验证参数')}catch(e:any){notify(e.message,true)}}
function resetParams(){params.value=Object.fromEntries(Object.entries(state.value.parameters||{}).map(([k,v]:any)=>[k,v.default]))}
const resultCloud=shallowRef<ResultCloud|null>(null),cloudLoading=ref(false),cloudError=ref('')
let cloudRequest:AbortController|undefined
let pollTimer:any,replayTimer:any,debounce:any,cloudToken=0,polling=false,disposed=false,replayEpoch=0,pollEpoch=0,detailsToken=0,flowReplayPending=false
let cloudSummary:ReturnType<typeof summarizeResultCloud>|null=null
function applyCloudSummary(){if(cloudSummary&&details.value?.id===selected.value)Object.assign(details.value,cloudSummary)}
function resetCloud(){cloudSummary=null;cloudRequest?.abort();cloudToken++;resultCloud.value=null;cloudLoading.value=false;cloudError.value=''}
async function loadCloud(){
 if(disposed||tab.value!==2||resultMode.value!=='points'||!selected.value||cloudLoading.value||resultCloud.value||cloudError.value||active.value===selected.value)return
 const token=cloudToken,name=selected.value;cloudRequest=new AbortController();cloudLoading.value=true
 try{
  const r=await fetch(`/api/scan3d/runs/${encodeURIComponent(name)}/cloud.bin`,{signal:cloudRequest.signal,cache:'no-cache'})
  if(!r.ok){const d=await r.json().catch(()=>({}));throw Error(d.detail||`完整点云加载失败（${r.status}）`)}
  const data=parseResultCloud(await r.arrayBuffer())
  if(token===cloudToken&&name===selected.value&&!disposed){resultCloud.value=data;cloudSummary=summarizeResultCloud(data);applyCloudSummary()}
 }catch(e:any){if(token===cloudToken&&e.name!=='AbortError')cloudError.value=errorZh(e)}
 finally{if(token===cloudToken)cloudLoading.value=false}
}
function retryCloud(){resetCloud();void loadCloud()}
async function selectRun(){
 index.value=0;audit.value=null;details.value=null;resetCloud();const name=selected.value,token=++detailsToken
 if(tab.value===2)void loadCloud()
 try{const d=await api(`/runs/${name}/details?include_cloud=false`);if(disposed||name!==selected.value||token!==detailsToken)return;details.value=d;applyCloudSummary();if(tab.value===3){await nextTick();if(replaying.value)flowReplayPending=true;else void replay()}}catch(e:any){if(!disposed&&name===selected.value&&token===detailsToken)notify(e.message,true)}
}
let historyPolling=false,historyTimer:any,monitorTimer:any,monitorStateTimer:any
async function poll(){
 if(polling||disposed)return;polling=true;const generation=pollEpoch
 try{
  const status=await api('/status');if(generation!==pollEpoch||disposed)return
  state.value=status;online.value=true
  const next=status.active||(!monitorId.value?status.helper?.last_job:'')
  if(next&&next!==monitorId.value)monitor.bind(next,status.scan?.id===next?status.scan:{status:status.active?'starting':'loading'})
  if(!Object.keys(params.value).length)resetParams()
 }catch{if(generation===pollEpoch)online.value=false}
 finally{polling=false}
}
async function pollHistory(){
 if(historyPolling||disposed)return;historyPolling=true
 try{
  const list=await api('/runs');if(disposed)return;runs.value=list
  if(!selected.value&&list.length){selected.value=monitorId.value||list[0].id;if(tab.value!==1)await selectRun()}
  const summary=list.find((r:any)=>r.id===selected.value)
  const changed=!details.value||details.value.id!==selected.value||summary?.state!==details.value.state?.status||(summary?.completed??0)!==(details.value.state?.completed_positions??0)||(summary?.elapsed??null)!==(details.value.state?.elapsed_seconds??null)
  if(tab.value===2&&selected.value&&selected.value!==active.value&&changed){const name=selected.value,token=detailsToken;const d=await api(`/runs/${name}/details?include_cloud=false`);if(!disposed&&name===selected.value&&token===detailsToken){const changedCloud=details.value&&((details.value.state?.completed_positions??0)!==(d.state?.completed_positions??0)||details.value.state?.status!==d.state?.status);details.value=d;if(changedCloud)resetCloud();else applyCloudSummary()}}
  if(tab.value===2)void loadCloud()
 }catch(e){console.debug('scan3d-history',e)}finally{historyPolling=false}
}
let cameraPolling=false,cameraTimer:any
async function pollCamera(){if(cameraPolling||disposed)return;cameraPolling=true;try{const r=await fetch('/api/status',{cache:'no-store',signal:AbortSignal.timeout(3000)});if(!r.ok)throw Error();device.value=await r.json();camera.value=device.value.camera||{}}catch{camera.value={online:false};device.value={}}finally{cameraPolling=false}}
watch(tab,()=>{monitor.setEnabled(tab.value===1);if(tab.value===0||tab.value===2||tab.value===3){void pollHistory();if(selected.value)void selectRun()}})
watch(resultMode,()=>{if(resultMode.value==='points')void loadCloud();else if(cloudLoading.value)resetCloud()})
async function readCamera(){try{cameraInfo.value=(await api('/camera-controls')).camera_controls}catch(e:any){notify(e.message,true)}}
function finishReplay(epoch:number,req:{run:string,index:number,laser:string},error?:any){
 if(disposed||epoch!==replayEpoch)return
 replaying.value=false
 const pending=flowReplayPending;flowReplayPending=false
 if(error&&selected.value===req.run&&index.value===req.index&&laser.value===req.laser)notify(error.message,true)
 if(pending&&tab.value===3)void replay()
}
async function replay(){
 if(!selected.value||replaying.value||historyLocked.value||!replayPositions.value.includes(index.value))return
 replaying.value=true;const epoch=++replayEpoch
 const req={run:selected.value,index:index.value,laser:laser.value,mode:'current_scan'}
 try{
  const r=await api('/replay',req,AbortSignal.timeout(15000))
  let pollFailures=0
  const check=async()=>{
   if(disposed||epoch!==replayEpoch)return
   try{
    const d=await api('/replay/'+r.id)
    if(disposed||epoch!==replayEpoch)return
    pollFailures=0
    if(d.status==='running'){replayTimer=setTimeout(check,700);return}
    if(d.status==='failed'){finishReplay(epoch,req,Error(d.error));return}
    if(selected.value===req.run&&index.value===req.index&&laser.value===req.laser){
     audit.value={...d,_id:r.id};profileRow.value=Math.max(d.roi[1],Math.min(d.roi[3]-1,profileRow.value));stage.value=d.steps.length-1
     notify(`当前策略回放完成：${d.final_count} 个最终点；历史点云未覆盖`)
    }
    finishReplay(epoch,req)
   }catch(e:any){
    if(disposed||epoch!==replayEpoch)return
    if(++pollFailures<=3){replayTimer=setTimeout(check,1500);return}
    finishReplay(epoch,req,Error('读取回放结果连续失败，请稍后重新分析：'+e.message))
   }
  }
  void check()
 }catch(e:any){finishReplay(epoch,req,e.name==='TimeoutError'?Error('提交回放请求超时，请稍后重试；未自动重复提交'):e)}
}
watch([index,laser],()=>{audit.value=null;clearTimeout(debounce);if(autoReplay.value&&!historyLocked.value)debounce=setTimeout(replay,800)})
const renameOpen=ref(false),renameWorking=ref(false),renameTitle=ref(''),renameTarget=ref(''),renameError=ref(''),renameInput=ref<HTMLInputElement>()
async function openRename(){renameTarget.value=selected.value;renameTitle.value=runs.value.find(r=>r.id===selected.value)?.title||'';renameError.value='';renameOpen.value=true;await nextTick();renameInput.value?.focus();renameInput.value?.select()}
async function saveRename(){
 if(renameWorking.value)return;renameWorking.value=true;busy.value=true;renameError.value='';pollEpoch++
 try{const d=await api(`/runs/${renameTarget.value}/rename`,{title:renameTitle.value});pollEpoch++;runs.value=runs.value.map(r=>r.id===d.id?{...r,title:d.title}:r);if(details.value?.id===d.id)details.value={...details.value,state:{...details.value.state,title:d.title,object_name:d.title}};renameOpen.value=false;notify('模型名称已更新');await poll()}
 catch(e:any){renameError.value=errorZh(e)}finally{renameWorking.value=false;busy.value=false}
}
async function archive(){busy.value=true;try{const d=await api(`/runs/${selected.value}/archive`,{});const link=document.createElement('a');link.href=d.url;link.download='';link.click();notify('模型与报告归档已生成，原始照片未删除')}catch(e:any){notify(e.message,true)}finally{busy.value=false}}

const cleanupOpen=ref(false),cleanupWorking=ref(false),cleanupName=ref(''),cleanupMode=ref('photos'),cleanupPlan=ref<any>(),cleanupStage=ref(0),cleanupAck=ref(false),cleanupError=ref('')
const cleanupTargetLocked=computed(()=>!!state.value.mesh_processing||!!cleanupName.value&&cleanupName.value===active.value)
const sizeText=(n:number)=>n>=1024**3?`${(n/1024**3).toFixed(2)} GiB`:n>=1024**2?`${(n/1024**2).toFixed(1)} MiB`:`${(n/1024).toFixed(1)} KiB`
function closeCleanup(){if(!cleanupWorking.value)cleanupOpen.value=false}
async function openCleanup(){if(historyLocked.value)return;cleanupName.value=selected.value;cleanupMode.value='photos';cleanupStage.value=0;cleanupAck.value=false;cleanupOpen.value=true;await previewCleanup()}
async function setCleanupMode(mode:string){cleanupMode.value=mode;cleanupAck.value=false;await previewCleanup()}
async function previewCleanup(){cleanupWorking.value=true;cleanupError.value='';cleanupPlan.value=null;try{cleanupPlan.value=await api(`/runs/${cleanupName.value}/cleanup-preview`,{mode:cleanupMode.value})}catch(e:any){cleanupError.value=errorZh(e)}finally{cleanupWorking.value=false}}
async function executeCleanup(){if(cleanupTargetLocked.value)return;cleanupWorking.value=true;cleanupError.value='';busy.value=true;try{const result=await api(`/runs/${cleanupName.value}/cleanup-execute`,{mode:cleanupMode.value,token:cleanupPlan.value.token,confirm:cleanupName.value,acknowledged:cleanupAck.value});cleanupOpen.value=false;if(cleanupMode.value==='all'&&monitorId.value===cleanupName.value)monitor.bind('');audit.value=null;details.value=null;selected.value='';resetCloud();meshes.value=await api('/meshes');mesh.value='';page.value=0;await poll();notify(`已删除 ${result.removed_files} 个文件，当前可用 ${(result.free_bytes/1024**3).toFixed(2)} GiB`)}catch(e:any){cleanupError.value=errorZh(e);cleanupPlan.value=null;cleanupStage.value=0;cleanupAck.value=false}finally{cleanupWorking.value=false;busy.value=false}}

onMounted(()=>{monitor.setEnabled(tab.value===1);void pollCamera();void poll();void pollHistory();cameraTimer=setInterval(pollCamera,2000);pollTimer=setInterval(poll,1800);historyTimer=setInterval(pollHistory,15000);monitorTimer=setInterval(()=>void monitor.refreshPoints(),700);monitorStateTimer=setInterval(()=>void monitor.refreshState(),1800);void Promise.allSettled([api('/replay-policy').then(x=>policy.value=x),api('/spatial-profile').then(x=>spatial.value=x),api('/meshes').then(x=>meshes.value=x)])})
onBeforeUnmount(()=>{disposed=true;monitor.dispose();resetCloud();clearInterval(historyTimer);clearInterval(monitorTimer);clearInterval(monitorStateTimer);clearInterval(pollTimer);clearInterval(cameraTimer);clearTimeout(replayTimer);clearTimeout(debounce);clearTimeout(toastTimer)})
</script>

<style scoped>
.spatial-controls{display:flex;flex-direction:column;gap:12px}.steps>button{padding:9px 12px}.spatial-controls label{font-size:13px}
.parameter-groups{flex-wrap:wrap}.parameter-groups button{min-width:45px}
</style>

<style scoped>
.light-motor-form{gap:10px}.light-motor-form>label:first-child{display:grid;grid-template-columns:1fr auto;gap:6px}.light-motor-form>label:first-child input{grid-column:1/3}.light-motor-form>.button-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.light-motor-form>.hint{font-size:11px}
</style>

<style scoped>
.policy-note{font-size:12px;line-height:1.7;padding:10px;background:#f2f0e6;border-radius:8px}.flow-explanation{white-space:normal;line-height:1.5;font-size:12px;min-height:55px}.field-grid input[readonly]{background:#f0f0e9;color:#555}.steps{overflow-y:auto}.steps button{flex-shrink:0}
.steps>button{flex:0 0 auto;min-height:60px;white-space:normal}.steps button div{min-width:0}.steps button b{line-height:1.45}.steps small{white-space:normal;line-height:1.4}.steps small span{display:block}
</style>
