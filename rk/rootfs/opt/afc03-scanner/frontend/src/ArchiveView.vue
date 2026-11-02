<template>
 <p v-if="error" class="error">{{error}}</p>
 <section class="work-card"><h2>扫描归档</h2><label class="field-label">记录<select v-model="selected" aria-label="归档扫描记录"><option v-for="s in scans" :value="s.id">{{s.title}} · {{s.id.slice(5,13)}} · {{s.status==='completed'?'采集完成':s.status}}</option><option v-for="s in datasets" :value="s.id">{{s.title}} · PC 历史导入</option></select></label>
 <template v-if="current"><p>{{current.title}}</p><template v-if="live"><p>采集状态：{{current.status==='completed'?'已完成':current.status}}；质量：<b>{{current.completion_verification?(current.completion_verification.passed?'内部检查通过':'需要复核'):'未完成自动核验'}}</b></p><p class="calibration-note" v-if="current.quality_warning">{{current.quality_warning}}</p>
 <div class="table-wrap" v-if="current.completion_verification"><table><thead><tr><th>检查项目</th><th>结果</th></tr></thead><tbody><tr v-for="c in current.completion_verification.checks"><td>{{names[c.name]||c.name}}</td><td>{{c.passed?'通过':'需复核'}}</td></tr></tbody></table></div></template>
 <p class="muted">模型尺寸单位为 mm；内部重复性检查不等于实际尺寸精度。原始照片保留在板卡；结果包包含模型、参数、质量报告、运动记录和原图哈希清单，不包含大体积原图。</p>
 <div class="actions"><a v-if="!live||current.geometry_available" :href="base+'/pointcloud'">下载点云</a><a v-if="!live||current.geometry_available" :href="base+'/mesh'">下载开放网格</a><a v-if="current.completion_verification" :href="base+'/audit'">完整核验报告</a><a v-if="current.archive" :href="base+'/archive'">下载结果归档 ZIP</a><a v-if="current.archive" :href="base+'/manifest'">文件校验清单</a></div></template></section>
 <section class="model-panel" v-if="current&&(!live||current.geometry_available)"><CloudView :key="selected" :dataset="selected" :collection="live?'scans':'datasets'"/><div class="model-footer">{{live?'RK3576 扫描结果':'PC 历史导入'}} · 保留缺测区域</div></section>
</template>
<script setup lang="ts">
import {ref,computed,onMounted,onBeforeUnmount} from 'vue'
import CloudView from './CloudView.vue'
const scans=ref<any[]>([]),datasets=ref<any[]>([]),selected=ref(''),error=ref('')
const live=computed(()=>selected.value.startsWith('live-')),current=computed(()=>[...scans.value,...datasets.value].find(s=>s.id===selected.value)),base=computed(()=>`/api/${live.value?'scans':'datasets'}/${selected.value}/files`)
const names:Record<string,string>={geometry_closure:'几何首尾重复性',geometry_records:'形状原图与运动记录',color_records:'颜色原图与运动记录',geometry_arrays:'点云及网格完整性',color_preserves_geometry:'颜色映射保持几何不变',color_encoder_alignment:'两圈编码器对应关系',color_closure:'颜色首尾照片对齐',operator_validity:'扫描有效性标记',operator_annotation:'人工有效性记录',data_complete:'数据完整性'}
async function poll(){try{const a=await fetch('/api/scans'),b=await fetch('/api/datasets');if(!a.ok||!b.ok)throw Error('无法读取板端归档');scans.value=await a.json();datasets.value=await b.json();if(!selected.value)selected.value=scans.value[0]?.id||datasets.value[0]?.id||''}catch(e:any){error.value=e.message}}
let timer:ReturnType<typeof setInterval>;onMounted(()=>{poll();timer=setInterval(poll,5000)});onBeforeUnmount(()=>clearInterval(timer))
</script>
