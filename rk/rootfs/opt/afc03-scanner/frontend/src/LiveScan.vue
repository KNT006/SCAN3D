<template>
 <div class="scan-layout">
  <section class="work-card">
   <h2>完整视场与采集范围</h2>
   <div class="scan-camera"><CameraPreview :stream-id="streamId"><svg viewBox="0 0 1080 1920"><rect :x="displayRoi[0]" :y="displayRoi[1]" :width="displayRoi[2]-displayRoi[0]" :height="displayRoi[3]-displayRoi[1]" fill="none" stroke="#88ffaf" stroke-width="3"/></svg></CameraPreview></div>
   <p class="muted">绿框为激光提取范围；原始照片仍保存完整视场。范围应包住物体，并排除转盘和背景上的激光。</p>
   <div class="roi-fields" v-if="!active"><label v-for="(name,i) in ['左','上','右','下']">{{name}}<input type="number" v-model.number="roi[i]" :aria-label="'采集范围'+name"/></label></div>
  </section>
  <section class="work-card">
   <h2>板端完整扫描 <span class="validation-tag">试扫 → 形状 → 颜色</span></h2>
   <p class="muted">约 2° 一步，两次整圈；每个位置停稳后拍摄。前 6° 后先暂停，检查物体是否稳定。</p>
   <div v-if="error" class="error" role="alert">{{error}}</div>
   <template v-if="!active">
    <label class="field-label">本轮名称<input class="scan-title" v-model="title" maxlength="80"/></label>
    <label class="check"><input type="checkbox" v-model="fixed"/>物体已固定，旋转时不会倒落</label>
    <label class="check"><input type="checkbox" v-model="unchanged"/>相机和激光支架保持标定位置</label>
    <label class="check"><input type="checkbox" v-model="laserOff"/>激光已关闭，可以采背景</label>
    <button class="primary" :disabled="pending||!fixed||!unchanged||!laserOff" @click="start">开始本轮 · 先采背景</button>
   </template>
   <template v-if="current">
    <div class="progress-heading"><strong>{{stageText[current.stage]||current.stage}}</strong><span>{{current.progress||0}}%</span></div><progress :value="current.progress||0" max="100"/>
    <p>{{current.title}} <span class="muted">· {{current.id.slice(5,13)}}</span></p>
    <dl><div><dt>状态</dt><dd>{{stateText[current.status]||current.status}}</dd></div><div><dt>本阶段位置</dt><dd>{{current.completed_positions||0}} / 181</dd></div><div><dt>编码器角度</dt><dd>{{current.angle?.toFixed(3)??'—'}}°</dd></div><div v-if="current.quality&&current.phase!=='color'"><dt>有效激光行 / 重复差 P95</dt><dd>{{current.quality.points}} / {{current.quality.repeat.p95?.toFixed(2)}} px</dd></div></dl>
    <p v-if="current.error" class="error">{{current.error}}</p>
    <p v-if="current.quality_warning" class="calibration-note" role="status">{{current.quality_warning}}</p>
    <div class="scan-prompt" v-if="current.status==='failed'&&current.stop_verified&&current.error==='Laser stripe unstable between stationary frames'"><p>少部分激光行可能在两张照片间跳变。经检查后，可剔除不稳定行，并从已停下的位置重新取帧；程序不会重复该次转动。</p><label class="check"><input type="checkbox" v-model="resumeReady"/>物体、相机、激光支架未动，激光仍开启</label><button class="primary" :disabled="pending||!resumeReady" @click="resume">核对角度与画面后继续</button></div>
    <div v-if="current.status==='waiting'" class="scan-prompt">
     <template v-if="current.stage==='await_laser_on'"><p>背景已保存。请打开激光，保持物体和支架不动。</p><button class="primary" :disabled="pending" @click="action('laser_on')">激光已开 · 开始约 6° 试扫</button></template>
     <template v-if="current.stage==='await_trial_confirmation'"><p>约 6° 试扫已停稳。确认物体无倾倒、滑动，扫描过程中不要触碰设备。</p><button class="primary" :disabled="pending" @click="action('continue_geometry')">试扫稳定 · 继续剩余一圈</button></template>
     <template v-if="current.stage==='await_laser_off'"><p>形状已采集。请关闭激光，不移动物体；随后自动开低亮灯带，再转一圈采颜色。</p><button class="primary" :disabled="pending" @click="action('laser_off')">激光已关 · 开始颜色扫描</button><button class="text-button" :disabled="pending" @click="action('finish_geometry')">本轮只保留形状，结束</button></template>
    </div>
    <button v-if="active" class="stop-button" @click="stop" :disabled="stopping">{{stopping?'停止请求已提交，等待反馈':'停止扫描'}}</button>
    <p v-if="current.stop_verified===true">已收到停止反馈，编码器连续三次稳定。</p><p class="error" v-else-if="current.stop_verified===false">尚未确认电机停稳，请查看转盘；必要时关闭电机驱动电源。</p>
    <div class="calibration-note">沿用临时标定，实际尺寸精度尚未验证。模型保留遮挡和缺测造成的孔洞，不自动补齐上下端面。</div>
    <p v-if="current.completion_verification">质量核验：{{current.completion_verification.passed?'内部检查通过':'需要复核'}}（不代表实物尺寸精度）</p><div class="actions" v-if="current.archive"><a :href="`/api/scans/${current.id}/files/archive`">下载结果归档 ZIP</a><a :href="`/api/scans/${current.id}/files/audit`">完整核验报告</a></div><div class="actions" v-if="current.geometry_available"><a :href="`/api/scans/${current.id}/files/pointcloud`">下载{{current.real_color?'彩色':'几何'}}点云</a><a :href="`/api/scans/${current.id}/files/mesh`">下载开放网格</a><a :href="`/api/scans/${current.id}/files/summary`">质量记录</a></div>
   </template>
  </section>
 </div>
 <section class="model-panel" v-if="current?.geometry_available"><CloudView :key="current.id+current.real_color" :dataset="current.id" collection="scans"/><div class="model-footer">本轮在 RK3576 采集并计算 · {{current.summary?.point_count}} 点 · {{current.real_color?'实拍颜色':'按扫描角度着色'}}</div></section>
 <section class="work-card" v-if="scans.length"><h2>板端采集记录</h2><button class="text-button scan-history" v-for="s in scans" :key="s.id" @click="chosen=s.id">{{s.title}} · {{s.id.slice(5,13)}} · {{stateText[s.status]||s.status}}</button></section>
</template>
<script setup lang="ts">
import {ref,computed,onMounted,onBeforeUnmount} from 'vue'
import CloudView from './CloudView.vue'
import CameraPreview from './CameraPreview.vue'
defineProps<{streamId?:string}>()
const title=ref('摆件 · 板端扫描'),roi=ref([110,230,970,1030]),fixed=ref(false),unchanged=ref(false),laserOff=ref(false)
const scans=ref<any[]>([]),chosen=ref(''),error=ref(''),pending=ref(false),stopping=ref(false),resumeReady=ref(false)
const current=computed(()=>scans.value.find(s=>s.id===chosen.value)||scans.value[0])
const active=computed(()=>scans.value.some(s=>['queued','running','waiting','stopping'].includes(s.status)))
const displayRoi=computed(()=>active.value&&current.value?current.value.roi:roi.value)
const stageText:Record<string,string>={connecting:'连接与静止检查',capturing_background:'采集无激光背景',await_laser_on:'等待打开激光',moving:'转动并等待停稳',capturing_geometry:'采集形状',await_trial_confirmation:'试扫完成，等待确认',reconstructing_geometry:'板端重建形状',await_laser_off:'等待关闭激光',capturing_color:'采集颜色',mapping_color:'板端映射颜色',verifying_result:'板端核验与归档',completed:'本轮扫描完成',stopping:'发送停止并核对位置',ended:'本轮已结束'}
const stateText:Record<string,string>={queued:'准备中',running:'运行中',waiting:'等待确认',stopping:'正在停止',completed:'已完成',stopped:'已停止',failed:'已停下，需检查',stop_unverified:'停止反馈未确认',interrupted:'异常中断'}
async function api(url:string,body?:any){const r=await fetch(url,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const v=await r.json();if(!r.ok)throw Error(typeof v.detail==='string'?v.detail:JSON.stringify(v.detail));return v}
async function poll(){try{scans.value=await api('/api/scans');if(!active.value)stopping.value=false}catch(e:any){error.value='连接中断，无法确认状态：'+e.message}}
async function start(){pending.value=true;error.value='';try{const s=await api('/api/scans',{title:title.value,fixed:fixed.value,calibration_unchanged:unchanged.value,laser_off:laserOff.value,roi:roi.value});chosen.value=s.id;stopping.value=false;await poll()}catch(e:any){error.value=e.message}finally{pending.value=false}}
async function action(a:string){pending.value=true;error.value='';try{await api(`/api/scans/${current.value.id}/action`,{stage:current.value.stage,action:a});await poll()}catch(e:any){error.value=e.message}finally{pending.value=false}}
async function resume(){pending.value=true;error.value='';try{await api(`/api/scans/${current.value.id}/resume`,{unchanged_and_laser_on:resumeReady.value});await poll()}catch(e:any){error.value=e.message}finally{pending.value=false}}
async function stop(){const s=scans.value.find(s=>['queued','running','waiting','stopping'].includes(s.status));if(!s)return;stopping.value=true;try{await api(`/api/scans/${s.id}/stop`,{});chosen.value=s.id;await poll()}catch(e:any){error.value=e.message;stopping.value=false}}
let timer:ReturnType<typeof setInterval>;onMounted(()=>{poll();timer=setInterval(poll,2000)});onBeforeUnmount(()=>clearInterval(timer))
</script>
