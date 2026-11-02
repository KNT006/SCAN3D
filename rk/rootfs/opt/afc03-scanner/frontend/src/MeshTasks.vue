<template>
 <div class="mesh-workspace">
  <div class="mesh-config"><select v-model="source" aria-label="STL 点云来源"><option v-for="s in sources" :key="s.id" :value="s.id">{{labelText(s.label)}}</option><option v-if="!sources.length" value="">{{sourceLoading?'正在读取点云来源…':'此扫描暂无完整点云'}}</option></select><select v-model="quality" aria-label="STL 质量"><option value="standard">采样：标准　0.4 mm</option><option value="detail">采样：精细　0.25 mm</option></select><button class="primary" :disabled="locked||working||busy||!source" @click="start">生成 STL</button></div>
  <div v-if="!sourceLoading&&!sources.length&&sourceReason" class="mesh-error" role="status">{{sourceReason}}</div>
  <div class="mesh-tuning"><label>Poisson 深度<select v-model.number="depth" aria-label="Poisson 重建深度"><option v-for="d in [4,5,6,7,8]" :key="d" :value="d">{{d}}　{{({4:'整体轮廓',5:'更平滑',6:'平滑与细节',7:'原标准',8:'原精细'} as any)[d]}}</option></select></label><label>曲面降噪<select v-model.number="samples" aria-label="曲面降噪"><option :value="2">原设置　2</option><option :value="8">温和　8</option><option :value="16">较强　16</option></select></label></div>
  <div class="mesh-options"><label>碎片清理<select v-model="cleanup" aria-label="碎片清理"><option value="main">仅保留最大主体　单个摆件</option><option value="small">仅去微小碎片　保留分离附件</option><option value="none">全部保留</option></select></label><label><input type="checkbox" v-model="holes"/>修补三/四边小孔</label><label><input type="checkbox" v-model="cap"/>沿标定底部轮廓闭合</label></div>
  <div class="mesh-taskbar"><b class="mesh-open-label">查看已有 STL</b><select v-model="selected" aria-label="STL 任务"><option value="">选择已有模型</option><option v-for="t in tasks" :key="t.id" :value="t.id">{{statusName(t.status)}}　{{new Date(t.request.created*1000).toLocaleString()}}　深度 {{t.request.depth??(t.request.quality==='detail'?8:7)}} / 降噪 {{t.request.samples_per_node??2}}　{{labelText(t.request.source_label)}}</option></select><a v-if="task?.status==='complete'" :href="file('stl')" download>下载 STL</a><MuseumImport :task="task?.status==='complete'?selected:''" :run="run" :initial-name="runTitle||run" @imported="emit('imported',$event)"/><a v-if="task?.status==='complete'" :href="file('report')" target="_blank">报告</a><a v-if="task?.report?.original_stl_preserved && task?.report?.postprocess_version" :href="file('original')" download>处理前</a><a v-if="task?.report?.removed_fragments_file" :href="file('removed')" download>移除部分</a><button v-if="working" @click="cancel" :disabled="busy">取消生成</button></div>
  <div v-if="working" class="mesh-progress" role="status"><b>{{stages[task?.stage]||'准备任务'}}</b><span>已用 {{Number(task?.elapsed_seconds||0).toFixed(1)}} s　后台处理中</span></div>
  <div v-if="error||task?.error" class="mesh-error" role="alert">{{errorZh(error||task.error)}}</div>
  <div class="mesh-display" :class="{'with-report':!!task?.report}">
   <ScanScene :stl="task?.status==='complete'?file('stl'):!selected?legacyMesh:''" :key="task?.status==='complete'?selected:!selected?legacyMesh:''"/>
   <aside v-if="task?.report" class="mesh-summary" aria-label="STL 模型数据">
    <h3>模型数据</h3>
    <dl>
     <div><dt>三角面</dt><dd>{{task.report.triangles.toLocaleString()}}</dd></div>
     <div><dt>生成耗时</dt><dd>{{task.report.elapsed_seconds.toFixed(2)}} s</dd></div>
     <div><dt>输入点数</dt><dd>{{task.report.input_points.toLocaleString()}}</dd></div>
     <div><dt>建模点数</dt><dd>{{task.report.meshing_points.toLocaleString()}}</dd></div>
     <div><dt>重建深度</dt><dd>{{task.report.depth}}</dd></div>
     <div><dt>曲面降噪</dt><dd>{{task.report.samples_per_node??2}}</dd></div>
     <div class="mesh-bounds"><dt>STL 包围盒 / mm</dt><dd><span v-for="(x,i) in task.report.mesh_extents_mm" :key="i">{{['X','Y','Z'][i]}} <b>{{x.toFixed(2)}}</b></span></dd></div>
     <div><dt>封闭</dt><dd>{{task.report.watertight?'是':'否'}}</dd></div>
     <div><dt>非流形边</dt><dd>{{task.report.nonmanifold_edges}}</dd></div>
     <div><dt>边界边</dt><dd>{{task.report.boundary_edges}}</dd></div>
     <div><dt>移除碎片</dt><dd>{{task.report.components_removed}}</dd></div>
     <div><dt>自交检查</dt><dd>{{task.report.self_intersections_checked?(task.report.self_intersecting_faces===0?'通过':'发现相交'):'未检测'}}</dd></div>
    </dl>
   </aside>
  </div>
  <div class="mesh-legacy"><select v-model="legacyMesh" @change="selected=''" aria-label="历史独立 STL"><option value="">历史独立 STL（未与当前扫描绑定）</option><option v-for="m in legacy" :key="m.url" :value="m.url">{{m.name}}</option></select><a v-if="legacyMesh&&!selected" :href="legacyMesh" download>下载历史 STL</a></div>
 </div>
</template>
<script setup lang="ts">
import {errorZh} from './errorZh'
import {ref,computed,watch,onBeforeUnmount} from 'vue'
import ScanScene from './ScanScene.vue'
import MuseumImport from './MuseumImport.vue'
const emit=defineEmits<{imported:[id:string]}>()
const props=defineProps<{run:string,locked:boolean,runTitle?:string}>(),sources=ref<any[]>([]),source=ref(''),quality=ref('standard'),depth=ref(6),samples=ref(2),holes=ref(true),cap=ref(true),cleanup=ref('main'),tasks=ref<any[]>([]),selected=ref(''),busy=ref(false),error=ref(''),legacy=ref<any[]>([]),legacyMesh=ref('')
const task=computed(()=>tasks.value.find(t=>t.id===selected.value)),working=computed(()=>tasks.value.some(t=>['queued','running','stopping'].includes(t.status)))
const sourceLoading=ref(false),scanState=ref<any>(null)
const sourceReason=computed(()=>{const s=scanState.value;if(!s)return '';if(s.closure?.passed===false)return `首尾图像闭合检查未通过（P95 ${Number(s.closure.p95_px).toFixed(2)} px，阈值 ${Number(s.closure.limit_px).toFixed(2)} px），未生成合并点云，暂不能生成 STL。逐帧数据已保留，需先离线复核。`;if(s.error)return '未生成可用合并点云：'+errorZh(s.error);return s.status==='running'?'扫描尚在进行，请等待点云合并完成。':'此存档没有可用合并点云，请检查扫描完成状态与记录。'})
const stages:Record<string,string>={queued:'准备处理',load:'读取完整点云',voxel:'分块空间采样　保留原点云',prepare:'估计和统一法向',normals:'Screened Poisson 曲面重建',poisson:'整理网格与封底',mesh_check:'质量检查与保存'}
const labelText=(value:string)=>String(value||'').replace(/[·•]/g,'　')
const statusName=(s:string)=>({queued:'排队',running:'处理中',complete:'完成',failed:'失败',interrupted:'中断',cancelled:'已取消',stopping:'取消中'} as any)[s]||s
const file=(kind:string)=>`/api/scan3d/mesh-tasks/${selected.value}/files/${kind}`
let generation=0,disposed=false,timer:any
const requests=new Set<AbortController>()
function abortRequests(){for(const request of requests)request.abort();requests.clear()}
async function api(path:string,body?:any){
 const controller=new AbortController();requests.add(controller)
 const timeout=setTimeout(()=>controller.abort(),10000)
 try{const r=await fetch('/api/scan3d'+path,{cache:'no-store',signal:controller.signal,...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});const d=await r.json();if(!r.ok)throw Error(d.detail||'请求失败');return d}
 finally{clearTimeout(timeout);requests.delete(controller)}
}
async function refresh(g:number){if(disposed||g!==generation||!props.run)return;try{const data=await api(`/runs/${props.run}/mesh-tasks`);if(disposed||g!==generation)return;tasks.value=data;if(!selected.value&&data.length)selected.value=(data.find((t:any)=>t.status==='complete')||data[0]).id}catch(e:any){if(g===generation)error.value=errorZh(e)}finally{if(!disposed&&g===generation)timer=setTimeout(()=>refresh(g),1500)}}
// Saved models are independent of the potentially expensive source inventory.
watch(()=>props.run,()=>{
 const g=++generation,run=props.run;clearTimeout(timer);abortRequests()
 sources.value=[];tasks.value=[];selected.value='';source.value='';legacyMesh.value='';legacy.value=[];error.value='';scanState.value=null;sourceLoading.value=false;busy.value=false
 if(!run)return
 void refresh(g)
 sourceLoading.value=true
 void api(`/runs/${run}/mesh-sources`).then(s=>{
  if(g!==generation||disposed)return
  sources.value=s;source.value=s.find((x:any)=>x.id.startsWith('analysis-'))?.id||s[0]?.id||''
 }).catch((e:any)=>{if(g===generation&&!disposed)error.value=errorZh(e)})
 .finally(()=>{if(g===generation&&!disposed)sourceLoading.value=false})
 void api(`/runs/${run}/details?include_cloud=false`).then(d=>{if(g===generation&&!disposed)scanState.value=d.state}).catch(()=>{})
 void api('/meshes').then(l=>{if(g===generation&&!disposed)legacy.value=l}).catch(()=>{})
},{immediate:true})
watch(selected,()=>{error.value=''})
async function start(){busy.value=true;error.value='';const g=generation;try{const result=await api(`/runs/${props.run}/mesh-tasks`,{source:source.value,quality:quality.value,depth:depth.value,samples_per_node:samples.value,close_small_holes:holes.value,cap_base:cap.value,cleanup:cleanup.value});if(g!==generation)return;selected.value=result.id;const t=await api(`/mesh-tasks/${result.id}`);if(g===generation)tasks.value=[t,...tasks.value.filter(x=>x.id!==t.id)]}catch(e:any){if(g===generation&&!disposed)error.value=errorZh(e)}finally{if(g===generation&&!disposed)busy.value=false}}
async function cancel(){const t=tasks.value.find(t=>['queued','running','stopping'].includes(t.status));if(!t)return;const g=generation;busy.value=true;try{await api(`/mesh-tasks/${t.id}/stop`,{});if(g===generation&&!disposed)selected.value=t.id}catch(e:any){if(g===generation&&!disposed)error.value=errorZh(e)}finally{if(g===generation&&!disposed)busy.value=false}}
onBeforeUnmount(()=>{disposed=true;generation++;clearTimeout(timer);abortRequests()})
</script>
<style scoped>
.mesh-open-label{font-size:12px;white-space:nowrap}.mesh-workspace{display:flex;flex-direction:column;min-height:0;flex:1}.mesh-config,.mesh-taskbar{display:flex;gap:8px;padding:10px 14px;align-items:center;border-bottom:1px solid #e4e4da}.mesh-config select:first-child,.mesh-taskbar select{flex:1;min-width:0}.mesh-config select,.mesh-taskbar select,.mesh-legacy select{font-size:12px;padding:7px}.mesh-config button{white-space:nowrap;padding:8px 12px}.mesh-options{display:flex;flex-wrap:wrap;gap:12px;padding:4px 14px 10px;font-size:11px}.mesh-options select{max-width:210px;font-size:11px;padding:4px}.mesh-options label{display:flex;align-items:center;gap:4px}.mesh-options span{margin-left:auto;color:#7b7e70}.mesh-taskbar a{white-space:nowrap;color:#806042;font-size:12px}.mesh-progress{display:flex;justify-content:space-between;background:#f0edce;padding:10px 14px;font-size:12px}.mesh-error{background:#fff0e7;color:#98442d;padding:10px 14px;font-size:12px}.mesh-summary{display:grid;grid-template-columns:1fr;gap:5px;padding:10px 14px;font-size:12px;border-top:1px solid #deded1}.mesh-summary small{font-size:10px;color:#8a674b;line-height:1.5}.mesh-legacy{padding:6px 14px;display:flex;gap:8px}.mesh-legacy select{width:100%;min-width:0}.mesh-legacy a{white-space:nowrap;font-size:11px}
</style>
<style scoped>
.mesh-config select:first-child{width:0;flex:1 1 0;min-width:180px}.mesh-config select:nth-child(2){width:150px;flex:0 0 150px}.mesh-taskbar select{width:0;flex:1 1 0}
</style>

<style scoped>
.mesh-tuning{display:flex;align-items:center;gap:16px;padding:8px 14px;font-size:12px;border-bottom:1px solid #e4e4da}.mesh-tuning label{display:flex;align-items:center;gap:8px;white-space:nowrap}.mesh-tuning select{width:145px;font-size:12px;padding:6px}.mesh-tuning small{font-size:11px;color:#7b7e70;max-width:290px;line-height:1.5}.mesh-config select:nth-child(2){width:185px;flex-basis:185px}
</style>

<style scoped>
.mesh-display{display:grid;grid-template-columns:minmax(0,1fr);flex:1;min-height:0;min-width:0}
.mesh-display.with-report{grid-template-columns:minmax(0,1fr) 242px}
.mesh-display>.scene{min-width:0;min-height:0}
.mesh-display>.mesh-summary{display:flex;flex-direction:column;gap:12px;padding:16px 18px;border-top:0;border-left:1px solid #bed5cf;min-height:0;min-width:0}
.mesh-summary h3{font-size:18px;color:#244f4d;font-weight:500}
.mesh-summary dl{gap:9px}
.mesh-summary dl>div{font-size:12px;gap:10px;align-items:baseline}
.mesh-summary dt{color:#60766e}
.mesh-summary dd{color:#264d47;font-variant-numeric:tabular-nums}
.mesh-summary .mesh-bounds{display:block;padding:9px 0;border-top:1px solid #cbded8;border-bottom:1px solid #cbded8}
.mesh-bounds dd{display:flex;justify-content:space-between;gap:6px;margin-top:8px}
.mesh-bounds dd span{display:flex;flex-direction:column;gap:3px;text-align:left}
.mesh-bounds dd b{font-weight:500}
@media(max-height:850px){.mesh-display>.mesh-summary{padding:10px 14px;gap:8px}.mesh-summary dl{gap:5px}.mesh-summary .mesh-bounds{padding:5px 0}.mesh-summary h3{font-size:16px}}
</style>
