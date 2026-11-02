<template>
 <section class="work-card">
  <div class="section-heading"><div><h2>采集通路检查</h2><p class="muted">静止取图与历史照片回放，测量均在 RK3576 上完成。</p></div><button @click="load">刷新报告</button></div>
  <p v-if="error" class="muted">{{error}}</p>
  <template v-if="report">
   <p>{{report.conclusion}}</p>
   <div class="metric-grid"><div><small>本次取图</small><strong>{{report.capture.frames_received}} / {{report.capture.frames_requested}}</strong></div><div><small>位移比较标记</small><strong>{{report.capture.suspects}}</strong></div><div><small>低置信度比较</small><strong>{{report.capture.low_confidence}}</strong></div><div><small>算法一致性</small><strong>{{report.replay.all_exact?'逐点一致':'需检查'}}</strong></div></div>
   <div class="table-wrap"><table><thead><tr><th>操作</th><th>样本数</th><th>中位耗时</th><th>P95 耗时</th></tr></thead><tbody><tr v-for="row in report.rows" :key="row.label"><td>{{row.label}}</td><td>{{row.count}}</td><td>{{row.p50_ms.toFixed(1)}} ms</td><td>{{row.p95_ms.toFixed(1)}} ms</td></tr></tbody></table></div>
   <p class="muted">分项可能相互包含，不能直接相加；本次没有转动电机。有效图片长度不代表 DMA 帧边界已验证。</p>
   <ul><li v-for="item in report.findings" :key="item">{{item}}</li></ul>
   <a href="/api/diagnostics/latest" target="_blank" rel="noopener">查看完整检查摘要</a>
  </template>
 </section>
</template>
<script setup lang="ts">
import {ref,onMounted} from 'vue'
const report=ref<any>(null),error=ref('')
async function load(){error.value='';try{const r=await fetch('/api/diagnostics/latest');if(!r.ok)throw Error('尚无已完成的检查报告');report.value=await r.json()}catch(e:any){error.value=e.message}}
onMounted(load)
</script>
