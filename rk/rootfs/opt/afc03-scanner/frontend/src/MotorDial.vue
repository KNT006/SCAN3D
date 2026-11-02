<template>
 <div class="motor-dial">
  <div class="motor-heading"><b>转盘相对转动</b></div>
  <div class="segments"><button :disabled="disabled" :class="{chosen:direction===1}" @click="direction=1">↻ 顺时针</button><button :disabled="disabled" :class="{chosen:direction===-1}" @click="direction=-1">↺ 逆时针</button></div>
  <svg viewBox="0 0 220 220" role="slider" aria-label="转盘相对角度" tabindex="0" :aria-valuenow="degrees" aria-valuemin="0" aria-valuemax="360" :aria-disabled="disabled" @pointerdown="down" @pointermove="move" @pointerup="dragging=false" @pointercancel="dragging=false" @keydown="key">
   <circle cx="110" cy="110" r="83" class="track"/><path v-if="degrees>0" :d="arc" class="sweep"/>
   <g v-for="n in 12" :key="n" :transform="`rotate(${(n-1)*30} 110 110)`"><line x1="110" y1="21" x2="110" y2="28"/></g>
   <text x="110" y="15">0°</text><text x="207" y="115">{{direction===1?90:270}}°</text><text x="110" y="212">180°</text><text x="13" y="115">{{direction===1?270:90}}°</text>
   <line x1="110" y1="110" :x2="point[0]" :y2="point[1]" class="needle"/><circle :cx="point[0]" :cy="point[1]" r="7" class="knob"/>
   <circle cx="110" cy="110" r="40" class="hub"/><text x="110" y="108" class="value">{{degrees}}°</text><text x="110" y="127">{{direction===1?'顺时针':'逆时针'}}</text>
  </svg>
  <div class="angle-entry"><label>角度<input aria-label="转动角度" type="number" min="0" max="360" step="0.1125" :disabled="disabled" v-model.number="degrees" @change="normalize"/></label><button v-for="v in [6,45,90,180,360]" :disabled="disabled" @click="degrees=v">{{v}}°</button></div>
  <div class="button-grid"><button class="primary" :disabled="disabled||!valid" @click="emit('turn',commandAngle)">转动 {{actual}}° {{direction===1?'↻':'↺'}}</button><button @click="emit('stop')">停止</button></div>
  <label class="reverse"><input type="checkbox" v-model="reverse" :disabled="disabled"/>方向反向</label>
 </div>
</template>
<script setup lang="ts">
import {ref,computed,watch} from 'vue'
const props=defineProps<{disabled:boolean}>(),emit=defineEmits<{turn:[angle:number],stop:[]}>()
const degrees=ref(6),direction=ref(1),reverse=ref(false)
try{reverse.value=localStorage.getItem('scan3d-motor-reverse')==='true'}catch{}
watch(reverse,v=>{try{localStorage.setItem('scan3d-motor-reverse',String(v))}catch{}})
let dragging=false
const valid=computed(()=>Number.isFinite(degrees.value)&&degrees.value>=.1125&&degrees.value<=360)
const actual=computed(()=>valid.value?Number((Math.round(degrees.value/.1125)*.1125).toFixed(4)):0)
const commandAngle=computed(()=>actual.value*direction.value*(reverse.value?-1:1))
const point=computed(()=>{const a=degrees.value*direction.value*Math.PI/180;return [110+83*Math.sin(a),110-83*Math.cos(a)]})
const arc=computed(()=>degrees.value>=360?`M110 27 A83 83 0 1 ${direction.value===1?1:0} 110 193 A83 83 0 1 ${direction.value===1?1:0} 110 27`:`M110 27 A83 83 0 ${degrees.value>180?1:0} ${direction.value===1?1:0} ${point.value.join(' ')}`)
function normalize(){degrees.value=Number.isFinite(degrees.value)?Math.max(0,Math.min(360,degrees.value)):0}
function pick(e:PointerEvent){const r=(e.currentTarget as SVGElement).getBoundingClientRect();const a=Math.atan2(e.clientX-r.left-r.width/2,-(e.clientY-r.top-r.height/2))*180/Math.PI;degrees.value=Math.round((a*direction.value+360)%360)}
function down(e:PointerEvent){if(props.disabled||e.button!==0)return;dragging=true;(e.currentTarget as SVGElement).setPointerCapture(e.pointerId);pick(e)}
function move(e:PointerEvent){if(dragging&&!props.disabled)pick(e)}
function key(e:KeyboardEvent){if(props.disabled)return;if(['ArrowLeft','ArrowDown','ArrowRight','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();degrees.value=e.key==='Home'?0:e.key==='End'?360:degrees.value+(['ArrowRight','ArrowUp'].includes(e.key)?1:-1);normalize()}}
</script>
<style scoped>
.motor-dial{display:flex;flex-direction:column;gap:9px;border-top:1px solid #e2e2d8;padding-top:12px}.motor-heading{display:flex;justify-content:space-between;font-size:13px}.motor-heading span,.motor-dial small{font-size:10px;color:#858577}.motor-dial svg{width:190px;height:190px;align-self:center;touch-action:none;cursor:crosshair}.track{fill:#f5f3eb;stroke:#dddcd0;stroke-width:8}.sweep{fill:none;stroke:#e75838;stroke-width:8;stroke-linecap:round}.motor-dial line{stroke:#a3a192;stroke-width:1.5}.motor-dial .needle{stroke:#e75838;stroke-width:2}.knob{fill:#e75838;stroke:#fff;stroke-width:2}.hub{fill:#faf9f5}.motor-dial text{text-anchor:middle;fill:#6e7264;font-size:10px}.motor-dial .value{font-size:19px;font-weight:600;fill:#31382d}.angle-entry{display:flex;align-items:end;gap:4px}.angle-entry label{width:90px;font-size:11px}.angle-entry input{padding:6px}.angle-entry button{padding:7px 5px;font-size:10px}.reverse{display:flex;align-items:center;gap:5px;font-size:11px!important}.motor-dial .segments button{flex:1}.motor-dial small{line-height:1.5}@media(max-height:850px){.motor-dial svg{width:145px;height:145px}.motor-dial{gap:5px}}
</style>

<style scoped>
.motor-dial{gap:7px}.motor-dial .segments{padding:0}.motor-dial svg{width:160px;height:160px;flex:none}.angle-entry label{display:block!important}.angle-entry input{margin:0}.motor-dial .reverse{flex-direction:row;gap:5px;margin:0}.motor-dial .reverse input{margin:0}.motor-dial small{display:block}
</style>
