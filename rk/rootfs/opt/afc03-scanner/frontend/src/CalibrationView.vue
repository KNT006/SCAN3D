<template>
 <div class="notice">计算和原图保存均在 RK3576。先贴平棋盘格；相机固定后只移动棋盘格。激光仍需手动开关。</div>
 <p v-if="error" class="error" role="alert">{{error}}</p>
 <div class="scan-layout">
  <section class="work-card">
   <h2>标定向导 <span class="validation-tag">相机 → 激光 → 转轴</span></h2>
   <template v-if="!active">
    <label class="field-label">标定项目<select v-model="kind" aria-label="标定项目"><option value="camera">1 · 相机内参</option><option value="laser">2 · 激光平面</option><option value="axis">3 · 转台旋转轴</option></select></label>
    <div class="roi-fields"><label>内角点列<input type="number" v-model.number="cols" min="3" max="20"/></label><label>内角点行<input type="number" v-model.number="rows" min="3" max="20"/></label><label>方格边长 mm<input type="number" v-model.number="square" min="1" step="0.1"/></label></div>
    <p class="muted">默认 8 × 6 个内角点、实测方格 11 mm。内角点数不是方格数。</p>
    <label v-if="kind!=='camera'" class="field-label">采用的相机参数<select v-model="camera" aria-label="相机参数来源"><option value="legacy">现用临时内参</option><option v-for="s in cameraCandidates" :value="s.id">{{s.title}} · {{s.id.slice(4,12)}}</option></select></label>
    <label class="check"><input type="checkbox" v-model="ready"/>棋盘格已贴平在硬板上，激光关闭，相机固定</label>
    <button class="primary" :disabled="pending||!ready" @click="create">建立标定会话</button>
   </template>
   <template v-if="current">
    <h3>{{current.title}}</h3><p>状态：{{statusText[current.status]||current.status}} · 已采 {{current.captures||0}} 个姿态（训练 {{current.training||0}} / 验证 {{current.held_out||0}}）</p>
    <p v-if="current.kind==='camera'">保持相机和镜头不动，让棋盘格完整入镜，分别前后倾、左右偏转，并覆盖画面不同区域。至少 8 个训练姿态与 2 个独立验证姿态。</p>
    <p v-else-if="current.kind==='laser'">每个姿态依次采：关激光、灯带亮的棋盘格 → 关激光、暗背景 → 开激光的照片。三张期间棋盘格与支架不动。至少 3 个不同距离／倾角的训练姿态和 1 个验证姿态。</p>
    <p v-else>棋盘格刚性固定在转盘上，先采原位，再每次点动约 15° 后采图。至少 4 个训练角度和 1 个独立验证角度，训练跨度不少于 30°。最多点动至 90°，不自动回零。</p>
    <p class="error" v-if="current.last_error||current.error">{{current.last_error||current.error}}</p>
    <template v-if="current.status==='waiting'">
     <div class="scan-prompt"><b>下一步：{{stageLabel}}</b>
      <label class="check" v-if="current.next_stage==='pattern'"><input type="checkbox" v-model="heldOut"/>此姿态仅用于独立验证，不参与拟合</label>
      <label class="check"><input type="checkbox" v-model="confirmed"/>{{current.next_stage==='laser_on'?'激光已开':'激光已关'}}，棋盘格与支架已就位且停稳</label>
      <button class="primary" :disabled="pending||!confirmed" @click="command('capture')">{{stageLabel}}</button>
      <button v-if="current.kind==='axis'" class="secondary" :disabled="pending||!confirmed||!current.captures||(current.move_count||0)>=6" @click="command('move')">单次低速转动约 15°</button>
      <button v-if="current.kind==='laser'&&current.next_stage!=='pattern'" class="text-button" :disabled="pending" @click="command('discard_pose')">放弃本组姿态，保留原图并重新采</button>
     </div>
     <div class="actions"><button class="primary" :disabled="pending||current.next_stage!=='pattern'" @click="command('solve')">计算并验证标定</button><button class="secondary" :disabled="pending" @click="command('finish')">保存并结束会话</button></div>
    </template>
    <button v-if="isActive(current)" class="stop-button" :disabled="pending" @click="stop">停止标定／停止电机</button>
    <p v-if="current.stop_verified===true">已核对编码器停稳。</p><p v-else-if="current.stop_verified===false" class="error">尚未确认电机停稳，请现场检查。</p>
    <div v-if="current.result" class="calibration-note"><p v-for="reason in current.result.review_reasons">{{reason}}</p><b>{{current.result.passed?'内部验证通过，尚未启用':'未通过检查，保留数据供复核'}}</b><p>相机训练误差：{{number(current.result.rms_px??current.result.training_rms_px)}} px；验证最大误差：{{number(current.result.held_out_rms_max_px)}} px</p><p v-if="current.kind==='laser'">训练／验证最大 P95：{{number(current.result.training_p95_max_mm)}} / {{number(current.result.held_out_p95_max_mm)}} mm</p><a :href="`/api/calibrations/${current.id}/files/result`">下载完整参数与逐姿态报告</a><p>这些检查反映内部一致性，不代表实物尺寸精度认证。</p></div>
   </template>
  </section>
  <section class="work-card"><h2>相机与角点</h2><div class="camera-wrap"><CameraPreview :stream-id="streamId"/></div><template v-if="current?.captures"><p class="muted">最近一张已检测的棋盘格角点；新姿态以实时画面为准。</p><img class="cal-corners" :src="`/api/calibrations/${current.id}/files/preview?t=${current.captures}`" alt="棋盘格角点检测结果"/></template></section>
 </div>
 <section class="work-card"><h2>标定记录</h2><p v-if="!sessions.length" class="muted">暂无板端标定；现用临时参数已保留。</p><button v-for="s in sessions" class="scan-history text-button" @click="chosen=s.id;confirmed=false">{{s.title}} · {{statusText[s.status]||s.status}} · {{s.result?(s.result.passed?'验证通过':'需复核'):'未求解'}}</button></section>
 <section class="work-card"><h2>启用匹配的标定版本</h2><p>当前版本：{{activeVersion}}。新扫描会复制当前版本，历史扫描不受切换影响。使用新相机内参时，必须用同一内参重新计算激光和转轴。</p>
  <div class="roi-fields"><label>相机<select v-model="bundleCamera"><option value="legacy">现用临时内参</option><option v-for="s in cameraCandidates" :value="s.id">{{s.title}} · {{s.id.slice(4,12)}}</option></select></label><label>激光<select v-model="bundleLaser"><option value="">请选择</option><option v-for="s in candidates('laser')" :value="s.id">{{s.title}} · {{s.id.slice(4,12)}}</option></select></label><label>转轴<select v-model="bundleAxis"><option value="">请选择</option><option v-for="s in candidates('axis')" :value="s.id">{{s.title}} · {{s.id.slice(4,12)}}</option></select></label></div>
  <label class="check"><input type="checkbox" v-model="activationConfirmed"/>已检查报告，相机、激光和转台位置与这些参数对应</label><button class="primary" :disabled="pending||!!active||!activationConfirmed||!bundleLaser||!bundleAxis" @click="activateBundle">生成版本并用于后续扫描</button>
  <p class="muted">恢复旧版本同样需要确认结构位置相符。</p><div v-for="v in versions" class="actions"><span>{{v.title}} {{v.id===activeVersion?'（当前）':''}}</span><button class="text-button" :disabled="pending||!!active||!activationConfirmed||v.id===activeVersion" @click="restore(v.id)">切换到此版本</button></div>
 </section>
</template>
<script setup lang="ts">
import {ref,computed,onMounted,onBeforeUnmount} from 'vue'
import CameraPreview from './CameraPreview.vue'
defineProps<{streamId?:string}>()
const sessions=ref<any[]>([]),versions=ref<any[]>([]),activeVersion=ref(''),chosen=ref(''),kind=ref('camera'),cols=ref(8),rows=ref(6),square=ref(11),camera=ref('legacy'),ready=ref(false),confirmed=ref(false),heldOut=ref(false),pending=ref(false),error=ref(''),activationConfirmed=ref(false),bundleCamera=ref('legacy'),bundleLaser=ref(''),bundleAxis=ref('')
const isActive=(s:any)=>['queued','running','waiting','stopping'].includes(s.status)
const active=computed(()=>sessions.value.find(isActive)),current=computed(()=>sessions.value.find(s=>s.id===chosen.value)||active.value||sessions.value[0])
const candidates=(k:string)=>sessions.value.filter(s=>s.kind===k&&s.result?.passed),cameraCandidates=computed(()=>candidates('camera'))
const stageLabel=computed(()=>current.value?.kind!=='laser'?'采集当前棋盘格':({pattern:'关激光，采棋盘格姿态',background:'保持激光关闭，采暗背景',laser_on:'打开激光，采激光线'}[current.value?.next_stage as string]||'采集'))
const statusText:Record<string,string>={queued:'准备中',waiting:'等待操作',running:'板端处理中',completed:'已保存',stopped:'已停止',failed:'失败',interrupted:'中断',stopping:'正在停止'}
const number=(v:any)=>typeof v==='number'?v.toFixed(3):'—'
async function api(path:string,body?:any){const r=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:JSON.stringify(d.detail));return d}
async function poll(){try{const d=await api('/api/calibrations');sessions.value=d.sessions;versions.value=d.versions;activeVersion.value=d.active}catch(e:any){error.value=e.message}}
async function run(fn:()=>Promise<any>){pending.value=true;error.value='';try{await fn();await poll()}catch(e:any){error.value=e.message}finally{pending.value=false}}
async function create(){await run(async()=>{const d=await api('/api/calibrations',{kind:kind.value,title:({camera:'相机内参',laser:'激光平面',axis:'转台旋转轴'} as any)[kind.value]+' · '+new Date().toLocaleString(),pattern:[cols.value,rows.value],square_mm:square.value,camera_source:camera.value,laser_off:ready.value,rigid_board:ready.value});chosen.value=d.id;confirmed.value=false;ready.value=false})}
async function command(action:string){await run(async()=>{const s=current.value;await api(`/api/calibrations/${s.id}/command`,{token:s.token,action,stage:s.next_stage||'pattern',held_out:heldOut.value,laser_on:s.next_stage==='laser_on',stationary_confirmed:confirmed.value});confirmed.value=false})}
async function stop(){await run(()=>api(`/api/calibrations/${current.value.id}/stop`,{}))}
async function activateBundle(){await run(async()=>{await api('/api/calibration-versions',{camera:bundleCamera.value,laser:bundleLaser.value,axis:bundleAxis.value,confirmed:activationConfirmed.value});activationConfirmed.value=false})}
async function restore(id:string){await run(async()=>{await api(`/api/calibration-versions/${id}/activate`,{confirmed:activationConfirmed.value});activationConfirmed.value=false})}
let timer:ReturnType<typeof setInterval>;onMounted(()=>{poll();timer=setInterval(poll,2500)});onBeforeUnmount(()=>clearInterval(timer))
</script>
