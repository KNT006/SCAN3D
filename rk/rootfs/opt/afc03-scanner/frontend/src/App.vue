<template>
 <div class="app-shell">
  <aside class="sidebar">
   <div class="brand"><div class="brand-mark">A</div><div>AFC03 <small>三维扫描工作台</small></div></div>
   <div class="sidebar-section">工作空间</div>
   <button v-for="item in tabs" :key="item.id" class="nav-button" :class="{active:tab===item.id}" @click="tab=item.id"><span>{{item.icon}}</span>{{item.label}}</button>
   <div class="sidebar-foot"><span class="live-dot" :class="{off:!online}"></span>{{online?'RK3576 已连接':'板卡连接中断'}}<small>连续预览版 · P3</small></div>
  </aside>
  <main>
   <header><div><div class="eyebrow">AFC03 / {{tabs.find(t=>t.id===tab)?.label}}</div><h1>{{titles[tab]}}</h1></div><span class="pill">计算运行于 RK3576</span></header>
   <div class="notice">采集与重建运行于板卡。完整扫描先进行约 6° 试扫；激光开关由人工确认。</div>
   <div v-if="error" class="error" role="alert">{{error}}</div>
   <div v-show="tab==='scan'"><LiveScan :stream-id="status?.camera?.stream_id"/></div>
   <ArchiveView v-if="tab==='results'"/>
   <CalibrationView v-if="tab==='calibration'" :stream-id="status?.camera?.stream_id"/>
   <template v-if="tab==='rebuild'">
    <section class="work-card"><div class="section-heading"><div><h2>从原始照片重建</h2><p class="muted">362 张照片 → 激光线 → 三维点云 → 主体网格 → PC 基线核对</p></div><button class="primary" :disabled="busy||!online||starting" @click="startJob">{{starting?'正在提交…':busy?'板端正在重建':'开始离线重建'}}</button></div>
     <p>数据集：{{current?.title}}。每次结果单独保存，不覆盖原始数据。</p>
     <template v-if="latest"><div class="progress-heading"><strong>{{stageName(latest.stage)}}</strong><span>{{latest.progress || 0}}%</span></div><progress :value="latest.progress || 0" max="100"></progress><p class="muted">{{statusName(latest.status)}}<span v-if="latest.processed_positions"> · 已处理 {{latest.processed_positions}} / 181 个位置</span></p><p v-if="latest.error" class="error">{{latest.error}}</p></template>
    </section>
    <section class="work-card" v-if="latest?.validation"><h2>跨平台计算验证 <span class="validation-tag" :class="{failed:!latest.validation.passed}">{{latest.validation.passed?'通过':'需检查'}}</span></h2>
     <div class="metric-grid"><div><small>总用时</small><strong>{{fmt(latest.validation.elapsed_seconds)}} <em>s</em></strong></div><div><small>进程峰值内存</small><strong>{{fmt(latest.validation.peak_rss_mib)}} <em>MiB</em></strong></div><div><small>点云最大坐标差</small><strong>{{scientific(latest.validation.point_distance_max_mm)}} <em>mm</em></strong></div><div><small>网格连接关系</small><strong>{{latest.validation.mesh_faces_equal?'一致':'不同'}}</strong></div></div>
     <p class="muted">以上表示同一输入的计算一致性，不表示实际扫描尺寸精度。重建部分使用本轮绑定的临时标定参数。</p>
     <div class="actions"><a :href="`/api/jobs/${latest.id}/files/validation`">下载验证报告</a><a :href="`/api/jobs/${latest.id}/files/pointcloud`">下载板端点云</a><a :href="`/api/jobs/${latest.id}/files/mesh`">下载板端网格</a></div>
    </section>
    <section class="work-card" v-if="jobs.length"><h2>任务记录</h2><div class="table-wrap"><table><thead><tr><th>任务编号</th><th>状态</th><th>进度</th><th>结果</th></tr></thead><tbody><tr v-for="j in jobs" :key="j.id"><td>{{j.id.slice(0,8)}}</td><td>{{statusName(j.status)}}</td><td>{{j.progress}}%</td><td><button class="text-button" @click="chosenJob=j.id">查看</button></td></tr></tbody></table></div></section>
   </template>
   <template v-if="tab==='device'">
    <DiagnosticsView/>
    <div class="device-layout"><section class="work-card"><h2>相机预览</h2><div class="camera-wrap"><CameraPreview v-if="status?.camera?.online" :stream-id="status?.camera?.stream_id"/><p v-else>相机暂未输出画面</p></div><p class="muted">完整视场缩放预览，不用于离线重建取帧。</p></section><section class="work-card"><h2>板卡状态</h2><dl><div><dt>计算主机</dt><dd>RK3576</dd></div><div><dt>相机</dt><dd>{{status?.camera?.online?'画面更新正常':'暂不可用'}}</dd></div><div><dt>硬件控制服务</dt><dd>{{(status?.controller_available??status?.serial_present)?'可连接':'未检测到'}}</dd></div><div><dt>可用内存</dt><dd>{{status?.memory_available_mib}} MiB</dd></div><div><dt>运动控制</dt><dd>分步确认后启动</dd></div></dl><p class="muted">控制服务可连接不代表电机已停稳。扫描前会核对运动状态，扫描期间独占控制模块。</p></section></div>
   </template>
   <footer>FPGA 图像通路 · RK3576 计算 · RK 硬件控制 <span>原始照片、编码器角度、标定随扫描保存</span></footer>
  </main>
 </div>
</template>
<script setup lang="ts">
import {ref,computed,onMounted,onBeforeUnmount} from 'vue'
import CloudView from './CloudView.vue'
import LiveScan from './LiveScan.vue'
import CalibrationView from './CalibrationView.vue'
import ArchiveView from './ArchiveView.vue'
import DiagnosticsView from './DiagnosticsView.vue'
import CameraPreview from './CameraPreview.vue'
type Tab='results'|'rebuild'|'device'|'scan'|'calibration'
const tabs=[{id:'calibration' as Tab,label:'标定向导',icon:'⊕'},{id:'scan' as Tab,label:'完整扫描',icon:'◎'},{id:'results' as Tab,label:'扫描结果',icon:'◈'},{id:'rebuild' as Tab,label:'离线重建',icon:'↻'},{id:'device' as Tab,label:'设备状态',icon:'▦'}]
const titles={calibration:'在板端，完成三个标定步骤',scan:'从实物，采集到三维模型',results:'让每一次扫描都可追溯',rebuild:'在板端，重新计算与验证',device:'图像与设备连接状态'}
const tab=ref<Tab>('scan'),datasets=ref<any[]>([]),selected=ref(''),jobs=ref<any[]>([]),chosenJob=ref(''),status=ref<any>(null),error=ref(''),online=ref(false),starting=ref(false)
const current=computed(()=>datasets.value.find(d=>d.id===selected.value)),latest=computed(()=>jobs.value.find(j=>j.id===chosenJob.value)||jobs.value[0]),busy=computed(()=>jobs.value.some(j=>['queued','running'].includes(j.status)))
const fmt=(v:number)=>Number.isFinite(v)?v.toFixed(1):'—',scientific=(v:number)=>Number.isFinite(v)?(v===0?'0':v.toExponential(2)):'—'
const stageName=(s:string)=>({queued:'等待处理',extracting:'提取激光线',reconstructing:'重建点云与网格',validating:'对照 PC 基线',completed:'计算完成',failed:'任务失败',interrupted:'任务中断'}[s]||s)
const statusName=(s:string)=>({queued:'已排队',running:'运行中',completed:'已完成',validation_failed:'计算差异超出阈值',failed:'失败',interrupted:'已中断'}[s]||s)
async function get(url:string,options?:RequestInit){const r=await fetch(url,options);if(!r.ok){const body=await r.json().catch(()=>({}));throw Error(body.detail||`请求失败 ${r.status}`)}return r.json()}
async function poll(){try{const [s,j]=await Promise.all([get('/api/status'),get('/api/jobs')]);status.value=s;jobs.value=j;online.value=true}catch{online.value=false}}
async function startJob(){starting.value=true;error.value='';try{const j=await get('/api/rebuild',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dataset_id:selected.value})});chosenJob.value=j.id;await poll()}catch(e:any){error.value=e.message}finally{starting.value=false}}
let timer:ReturnType<typeof setInterval>
onMounted(async()=>{try{datasets.value=await get('/api/datasets');selected.value=datasets.value[0]?.id||''}catch(e:any){error.value=e.message}await poll();timer=setInterval(poll,2000)})
onBeforeUnmount(()=>clearInterval(timer))
</script>
