<template>
 <div class="frame-stepper">
  <input v-model="draft" type="text" inputmode="numeric" role="spinbutton" aria-label="图像帧号"
   :aria-valuenow="modelValue" :aria-valuemin="positions[0]??0" :aria-valuemax="positions.at(-1)??0"
   :disabled="!positions.length" @change="commit" @blur="commit"
   @keydown.up.prevent="step(1)" @keydown.down.prevent="step(-1)" @keydown.enter.prevent="commit"/>
  <div class="frame-stepper-arrows">
   <button type="button" aria-label="下一保存帧" title="下一保存帧（可长按）" :disabled="!canStep(1)"
    @pointerdown.prevent="start($event,1)" @pointerup="stop" @pointercancel="stop" @lostpointercapture="stop"
    @click="keyboardClick($event,1)">▲</button>
   <button type="button" aria-label="上一保存帧" title="上一保存帧（可长按）" :disabled="!canStep(-1)"
    @pointerdown.prevent="start($event,-1)" @pointerup="stop" @pointercancel="stop" @lostpointercapture="stop"
    @click="keyboardClick($event,-1)">▼</button>
  </div>
 </div>
</template>
<script setup lang="ts">
import {ref,watch,onBeforeUnmount} from 'vue'
const props=defineProps<{modelValue:number,positions:number[]}>()
const emit=defineEmits<{(event:'update:modelValue',value:number):void}>()
const draft=ref(String(props.modelValue))
watch(()=>props.modelValue,value=>{draft.value=String(value)})
let timer:ReturnType<typeof setTimeout>|undefined
function next(direction:number){return direction>0?props.positions.find(i=>i>props.modelValue):[...props.positions].reverse().find(i=>i<props.modelValue)}
function canStep(direction:number){return next(direction)!==undefined}
function step(direction:number){const value=next(direction);if(value===undefined){stop();return}draft.value=String(value);emit('update:modelValue',value)}
function commit(){
 const value=Number(draft.value)
 if(!draft.value.trim()||!Number.isFinite(value)||!props.positions.length){draft.value=String(props.modelValue);return}
 const nearest=props.positions.reduce((best,i)=>Math.abs(i-value)<Math.abs(best-value)?i:best)
 draft.value=String(nearest);emit('update:modelValue',nearest)
}
function stop(){clearTimeout(timer);timer=undefined}
function start(event:PointerEvent,direction:number){
 if(event.button!==0)return
 stop();(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);step(direction)
 const repeat=()=>{step(direction);if(canStep(direction))timer=setTimeout(repeat,110)}
 timer=setTimeout(repeat,360)
}
function keyboardClick(event:MouseEvent,direction:number){if(event.detail===0)step(direction)}
onBeforeUnmount(stop)
</script>
<style scoped>
.frame-stepper{display:flex;flex:0 0 104px;min-width:104px;align-self:stretch;min-height:38px}
.frame-stepper input{box-sizing:border-box;width:74px!important;min-width:0;flex:1;padding:8px 10px!important;border-radius:9px 0 0 9px!important;font-size:14px!important;font-variant-numeric:tabular-nums}
.frame-stepper-arrows{display:flex;flex-direction:column;width:30px;flex:none}
.frame-stepper-arrows button{box-sizing:border-box;display:flex;align-items:center;justify-content:center;flex:1;min-width:30px;min-height:19px;padding:0!important;font-size:9px!important;line-height:1;touch-action:none;user-select:none;border-radius:0!important;border-left:0}
.frame-stepper-arrows button:first-child{border-radius:0 8px 0 0!important}
.frame-stepper-arrows button:last-child{border-radius:0 0 8px 0!important;border-top:0}
</style>
