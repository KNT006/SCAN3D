<template>
 <div class="ai-filter">
  <button class="secondary wide" :disabled="locked||pending||working||!available" @click="start">AI 去除离群点</button>
  <p v-if="reason">{{reason}}</p><p v-if="error" role="alert">{{error}}</p>
  <select v-if="tasks.length" v-model="selected" aria-label="AI 过滤任务"><option v-for="t in tasks" :key="t.id" :value="t.id">{{t.id.slice(0,8)}} · {{labels[t.status]||t.status}}</option></select>
  <template v-if="current">
   <p v-if="working">处理中…</p>
   <button v-if="working" class="secondary wide" :disabled="pending" @click="stop">取消 AI 过滤</button>
   <p v-if="current.error">{{current.error}}</p>
   <template v-if="current.status==='complete'">
    <button class="secondary wide" @click="emit('preview',current.id)">预览 AI 过滤点云</button>
    <button class="secondary wide original-cloud" @click="emit('preview','')">查看原始点云</button>
    <a :href="file('report')" target="_blank">过滤报告 ↗</a> · <a :href="file('npz')">下载点云</a>
   </template>
   <a :href="file('log')" target="_blank">运行日志 ↗</a>
  </template>
 </div>
</template>
<script setup lang="ts">
import {computed,ref,watch,onBeforeUnmount} from 'vue'
const props=defineProps<{run:string,locked:boolean}>(),emit=defineEmits<{preview:[id:string]}>()
const tasks=ref<any[]>([]),selected=ref(''),available=ref(false),reason=ref(''),error=ref(''),pending=ref(false)
const current=computed(()=>tasks.value.find(t=>t.id===selected.value)),working=computed(()=>tasks.value.some(t=>['queued','running'].includes(t.status)))
const labels:Record<string,string>={queued:'等待处理',running:'处理中',complete:'完成',failed:'失败',interrupted:'已中断',cancelled:'已取消'}
let generation=0,requestEpoch=0,disposed=false,timer:ReturnType<typeof setTimeout>
const file=(kind:string)=>`/api/scan3d/ai-filter/${selected.value}/files/${kind}`
async function api(path:string,post=false){const r=await fetch('/api/scan3d'+path,{method:post?'POST':'GET',cache:'no-store',signal:AbortSignal.timeout(15000)});const d=await r.json();if(!r.ok)throw Error(d.detail||'AI 任务请求失败');return d}
async function refresh(g=generation){const epoch=++requestEpoch;clearTimeout(timer);try{const d=await api(`/runs/${props.run}/ai-filter`);if(g!==generation||disposed||epoch!==requestEpoch)return;tasks.value=d.tasks;available.value=d.available;reason.value=d.reason;if(!tasks.value.some(t=>t.id===selected.value))selected.value=tasks.value[0]?.id||''}catch(e:any){if(g===generation&&epoch===requestEpoch)error.value=e.message}finally{if(g===generation&&!disposed&&epoch===requestEpoch)timer=setTimeout(()=>refresh(g),2500)}}
watch(()=>props.run,()=>{generation++;clearTimeout(timer);tasks.value=[];selected.value='';error.value='';reason.value='';available.value=false;if(props.run)void refresh()},{immediate:true})
async function start(){pending.value=true;error.value='';const g=generation;try{const d=await api(`/runs/${props.run}/ai-filter`,true);if(g!==generation)return;selected.value=d.id;clearTimeout(timer);await refresh(g)}catch(e:any){if(g===generation)error.value=e.message}finally{pending.value=false}}
async function stop(){const task=tasks.value.find(t=>['running','queued'].includes(t.status));if(!task)return;pending.value=true;try{await api(`/ai-filter/${task.id}/stop`,true);clearTimeout(timer);await refresh()}catch(e:any){error.value=e.message}finally{pending.value=false}}
onBeforeUnmount(()=>{disposed=true;generation++;clearTimeout(timer)})
</script>
<style scoped>
.ai-filter .original-cloud{margin-top:10px}

.ai-filter{margin:12px 0;padding:12px 0;border-top:1px solid var(--border,#d7dbce);border-bottom:1px solid var(--border,#d7dbce)}.ai-filter small{display:block;font-size:11px;line-height:1.6;opacity:.8}.ai-filter p{font-size:12px;line-height:1.6;margin:8px 0}.ai-filter select{width:100%;margin:8px 0;font:inherit}.ai-filter a{font-size:12px;color:inherit}
</style>
