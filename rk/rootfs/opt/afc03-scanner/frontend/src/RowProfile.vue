<template>
 <section class="row-review">
  <div class="row-controls"><b>行亮度剖面</b><button :disabled="!audit||row<=min" @click="emit('update:row',row-1)">上一行</button><label>y=<input aria-label="剖面行号" type="number" :value="row" :min="min" :max="max" @change="setRow" @blur="setRow" @keydown.enter="setRow"/></label><button :disabled="!audit||row>=max" @click="emit('update:row',row+1)">下一行</button></div>
  <div class="row-legend"><label v-for="c in curves" :key="c.key" :style="{color:c.color}"><input type="checkbox" v-model="enabled[c.key]"/>{{c.label}}</label></div>
  <div v-if="error" class="row-error">{{error}}</div>
  <svg v-if="data?.curves" class="profile-plot" viewBox="0 0 700 250" role="img" :aria-label="`第 ${row} 行差分亮度曲线`" @mousemove="hover" @mouseleave="hoverX=null">
   <rect x="45" y="12" width="630" height="196" fill="#fcfcf7"/>
   <g v-for="v in [0,64,128,192,255]" :key="v"><line x1="45" x2="675" :y1="sy(v)" :y2="sy(v)" stroke="#e1e2d8"/><text x="39" :y="sy(v)+4" text-anchor="end">{{v}}</text></g>
   <g v-for="v in ticks" :key="v"><text :x="sx(v)" y="229" text-anchor="middle">{{v}}</text></g>
   <rect v-if="peak?.core_lo!==undefined" :x="sx(peak.core_lo)" y="12" :width="Math.max(1,sx(peak.core_hi)-sx(peak.core_lo))" height="196" fill="#eccb4150"/>
   <g v-if="peak"><line v-for="x in [peak.lo,peak.hi]" :key="x" :x1="sx(x)" :x2="sx(x)" y1="12" y2="208" stroke="#8a8272" stroke-dasharray="3 3"/></g>
   <line v-if="data.baseline!==null" x1="45" x2="675" :y1="sy(data.baseline)" :y2="sy(data.baseline)" stroke="#9b8ac4" stroke-dasharray="4 3"/>
   <line x1="45" x2="675" :y1="sy(data.parameters.signal_min)" :y2="sy(data.parameters.signal_min)" stroke="#d17b36" stroke-dasharray="5 4"/>
   <line v-if="peak" x1="45" x2="675" :y1="sy(peak.threshold)" :y2="sy(peak.threshold)" stroke="#248dbc" stroke-dasharray="2 3"/>
   <path v-for="c in curves.filter(c=>enabled[c.key])" :key="c.key" :d="path(c.key)" fill="none" :stroke="c.color" :stroke-width="c.key==='signal'?1.8:1.3"/>
   <g v-for="r in data.records" :key="r.rid" @click="peakId=r.rid" class="peak-marker"><line :x1="sx(r.x)" :x2="sx(r.x)" y1="12" y2="208" :stroke="r.retained?'#258066':'#bd5743'" stroke-dasharray="2 3"/><circle :cx="sx(r.k)" :cy="sy(data.curves.smooth[r.k-data.x_origin])" r="4" :fill="r.retained?'#258066':'#bd5743'"/></g>
   <line v-if="hoverX!==null" :x1="sx(hoverX)" :x2="sx(hoverX)" y1="12" y2="208" stroke="#444"/>
   <text x="360" y="247" text-anchor="middle">x / 原始采集坐标（旋转后）</text>
  </svg>
  <div v-else class="profile-placeholder">{{loading?'正在读取剖面…':data?'此帧未保存激光 / 背景原图；下方仍可查看真实候选判定':'分析此帧后，可点击左图选行'}}</div>
  <div v-if="hoverText" class="profile-foot">{{hoverText}}</div>
  <template v-if="data">
   <div class="peak-select"><select v-model.number="peakId"><option v-for="r in data.records" :key="r.rid" :value="r.rid">峰 x={{r.x.toFixed(2)}}　{{r.decision}}</option><option v-if="!data.records.length" :value="-1">此行无条纹候选</option></select><b>{{data.final_uv.length}} 个最终点</b></div>
   <div v-if="peak" class="peak-metrics"><span>差分峰值 <b>{{peak.signalmax}}</b></span><span>局部 RGB 亮度 <b>{{peak.v?.toFixed(1)??'—'}}</b></span><span>亮区宽度 <b>{{peak.width}} px</b></span><span>转盘轴 Y <b>{{peak.axis_y_mm?.toFixed(3)??'—'}} mm</b></span><span>距转轴 <b>{{peak.radius_mm?.toFixed(2)??'—'}} mm</b></span><span>主 / RGB 阈值 <b>40 / {{peak.threshold}}</b></span><span :class="peak.retained?'pass':'reject'">最终：<b>{{peak.decision}}</b></span></div>
   <div v-if="peak" class="row-decisions"><span>主支路：{{peak.branches?.main.reason}}</span><span>RGB 支路：{{peak.branches?.adaptive.reason}}</span><span>{{peak.color_reliable?'局部颜色可靠':'局部颜色不可靠，RGB 支路回退 40'}} · {{data.color_source==='same_angle_raw_COLOR'?'来自同角度 COLOR 原图':'来自存档的 7×7 局部 RGB 统计'}}</span></div>
   <div v-if="peak?.near_peak" class="row-decisions"><b>近峰规则</b><span :class="peak.near_peak.gap<20?'pass':'reject'">{{peak.near_peak.gap<20?'✓':'✕'}} 距离 {{peak.near_peak.gap.toFixed(2)}} &lt;20 px</span><span :class="peak.near_peak.ratio<=.6?'pass':'reject'">{{peak.near_peak.ratio<=.6?'✓':'✕'}} 弱/强 {{peak.near_peak.ratio.toFixed(3)}} ≤0.60</span><span :class="peak.near_peak.stable?'pass':'reject'">{{peak.near_peak.stable?'✓':'✕'}} 强峰稳定 · 支持 {{peak.near_peak.anchor_rows}} 行</span></div>
   <div v-if="peak?.secondary_features" class="row-decisions"><b>弱宽次候选</b><span>间距 {{peak.secondary_features.gap.toFixed(2)}} px · 弱/强 {{peak.secondary_features.ratio.toFixed(3)}} · 重复侧支 {{peak.secondary_features.weak_branch_rows??0}} 行</span></div>
   <div v-if="peak?.long_track_suspect" class="row-decisions advisory"><b>长轨迹嫌疑 · 仅标记，未删除此点</b></div>
   <div class="profile-note">先去转盘：Y &gt; {{data.ground.min_axis_y_mm}} mm；再筛半径 ≤ {{data.spatial_filter.effective_radius_mm}} mm。旧多峰判定 / 分支恢复关闭。曲线橙虚线为主支路 40，蓝虚线为选中候选 RGB 阈值；原始突出度及亮核边界未存档，不作猜测。</div>
  </template>
 </section>
</template>
<script setup lang="ts">
import {errorZh} from './errorZh'
import {ref,computed,watch} from 'vue'
const props=defineProps<{audit:any,row:number}>(),emit=defineEmits(['update:row'])
const data=ref<any>(),error=ref(''),loading=ref(false),peakId=ref(-1),hoverX=ref<number|null>(null)
const min=computed(()=>props.audit?.roi?.[1]??0),max=computed(()=>(props.audit?.roi?.[3]??1920)-1),peak=computed(()=>data.value?.records.find((r:any)=>r.rid===peakId.value))
const curves=[{key:'signal',label:'真实差分',color:'#1d8065'},{key:'smooth',label:'平滑 /16',color:'#d17b36'},{key:'on',label:'激光开',color:'#777f8c'},{key:'off',label:'背景关',color:'#a592be'}],enabled=ref<Record<string,boolean>>({signal:true,smooth:true,on:false,off:false})
let generation=0
watch(()=>[props.audit?._id,props.row],async()=>{const g=++generation;data.value=null;error.value='';hoverX.value=null;if(!props.audit?._id)return;loading.value=true;try{const r=await fetch(`/api/scan3d/replay/${props.audit._id}/row/${props.row}`,{signal:AbortSignal.timeout(8000)});const d=await r.json();if(!r.ok)throw Error(d.detail);if(g!==generation)return;data.value=d;peakId.value=d.records.find((p:any)=>p.retained)?.rid??d.records[0]?.rid??-1}catch(e:any){if(g===generation)error.value=errorZh(e)}finally{if(g===generation)loading.value=false}},{immediate:true})
const sx=(x:number)=>45+630*(x-data.value.x_origin)/Math.max(1,data.value.curves.signal.length-1),sy=(v:number)=>208-196*v/255
const ticks=computed(()=>data.value?.curves?Array.from({length:6},(_,i)=>Math.round(data.value.x_origin+(data.value.curves.signal.length-1)*i/5)):[])
function path(k:string){return data.value.curves[k].map((v:number,i:number)=>`${i?'L':'M'}${sx(i+data.value.x_origin).toFixed(2)},${sy(v).toFixed(2)}`).join(' ')}
function setRow(e:Event){emit('update:row',Math.max(min.value,Math.min(max.value,Math.round(Number((e.target as HTMLInputElement).value)))))}
function hover(e:MouseEvent){const svg=e.currentTarget as SVGSVGElement;const pt=svg.createSVGPoint();pt.x=e.clientX;pt.y=e.clientY;const local=pt.matrixTransform(svg.getScreenCTM()!.inverse());hoverX.value=Math.max(data.value.x_origin,Math.min(data.value.x_origin+data.value.curves.signal.length-1,Math.round(data.value.x_origin+(local.x-45)/630*(data.value.curves.signal.length-1))))}
const hoverText=computed(()=>hoverX.value===null||!data.value?.curves?'':`x=${hoverX.value}　差分 ${data.value.curves.signal[hoverX.value-data.value.x_origin]}　平滑 ${data.value.curves.smooth[hoverX.value-data.value.x_origin].toFixed(2)}`)
</script>
<style scoped>
.row-review{display:flex;flex-direction:column;gap:10px;min-height:0;padding:14px 18px;font-size:12px}.row-controls{display:flex;align-items:center;gap:8px}.row-controls>b{margin-right:auto;font-size:15px}.row-controls input{width:74px;padding:5px}.row-controls button{padding:5px 8px}.row-legend{display:flex;gap:16px}.row-legend label{display:flex;align-items:center;gap:4px}.profile-plot{width:100%;height:auto;max-height:260px;flex:none}.profile-plot text{font:11px sans-serif;fill:#666}.profile-placeholder{height:240px;display:grid;place-items:center;color:#858575}.profile-foot,.profile-note{font-size:11px;line-height:1.5;color:#777b6d}.profile-foot{min-height:17px}.peak-select{display:flex;gap:12px;align-items:center}.peak-select select{min-width:0;flex:1;padding:7px}.peak-metrics{display:grid;grid-template-columns:1fr 1fr;gap:10px;background:#f2f0e6;padding:12px;border-radius:8px}.peak-metrics span{display:flex;justify-content:space-between;gap:8px}.row-decisions{display:flex;flex-wrap:wrap;gap:6px;line-height:1.6;border-top:1px solid #e3e3d9;padding-top:8px}.row-decisions>div{display:flex;flex-wrap:wrap;gap:12px}.row-decisions small{width:100%;color:#777}.pass{color:#26765e}.reject,.row-error{color:#a84535}.peak-marker{cursor:pointer}@media(max-height:850px){.row-review{gap:6px;padding:10px}.profile-plot{max-height:190px}.peak-metrics{padding:8px;gap:6px}}
</style>
<style scoped>
.row-review{gap:6px;padding:10px 18px;font-size:11px}.profile-plot{height:190px;max-height:190px}.row-controls>b{font-size:14px}.peak-metrics{padding:8px;gap:6px}.row-decisions{gap:4px;padding-top:5px}.row-legend{gap:12px}.profile-note{font-size:10px}.profile-foot{font-size:10px}
</style>

<style scoped>.row-review{overflow-y:auto}.advisory{color:#9a7018}.profile-placeholder{min-height:110px;height:150px;text-align:center;padding:15px}.row-decisions>span{display:block;width:100%}</style>
