<template>
 <section class="panel"><div class="panel-title"><h2>01 / 相机原始预览</h2></div>
  <div class="camera-box"><div class="paired-camera" ref="host"><div class="paired-frame" :style="{width:width+'px',height:height+'px'}"><canvas ref="canvas" :style="{width:height+'px',height:width+'px'}" aria-label="原始同帧预览"/><svg v-if="roi" viewBox="0 0 1080 1920" class="scan-roi" aria-label="当前扫描取景范围"><rect :x="roi[0]" :y="roi[1]" :width="roi[2]-roi[0]" :height="roi[3]-roi[1]" fill="none" stroke="#62dbc2" stroke-width="3"/></svg></div>
   <p v-if="waiting||failed" class="paired-badge">{{failed?'连接中断，正在恢复…':'正在连接相机…'}}</p><span v-else class="paired-badge">{{fps}} fps　{{lastFrame}}</span></div></div>
  <div class="panel-foot">原始预览</div>
 </section>
 <section class="panel"><div class="panel-title"><h2>02 / 颜色校正</h2></div>
  <div class="camera-box"><div class="paired-camera"><div class="paired-frame" :style="{width:width+'px',height:height+'px'}"><canvas ref="second" :style="{width:height+'px',height:width+'px'}" aria-label="同帧颜色校正预览"/></div>
   <p v-if="waiting||failed" class="paired-badge">{{failed?'连接中断，正在恢复…':'等待同帧校正…'}}</p><span v-else class="paired-badge">{{conditions}}</span></div></div>
  <div class="panel-foot">校正预览</div>
 </section>
</template>
<script setup lang="ts">
import {ref,computed,watch,onMounted,onBeforeUnmount} from 'vue'
import {MjpegParser} from './mjpeg'
const props=defineProps<{streamId?:string,roi?:number[]}>()
const second=ref<HTMLCanvasElement>(), profile=ref<any>(null)
const conditions=computed(()=>profile.value?.available?`试用　白灯 ${profile.value.profile.led} / 增益 ${profile.value.profile.gain} / 激光关`:'校正配置未加载')
const host=ref<HTMLDivElement>(),canvas=ref<HTMLCanvasElement>(),width=ref(0),height=ref(0),visible=ref(false),failed=ref(false),waiting=ref(true),lastFrame=ref(''),fps=ref('—'),mode=ref('stream')
let observer:ResizeObserver,intersection:IntersectionObserver,onscreen=true,disposed=false,generation=0,timer:any,controller:AbortController|undefined
let pending:{bytes:Uint8Array,g:number}|null=null,rendering=false,shown=0,windowStart=0
const current=(g:number)=>g===generation&&!disposed&&visible.value
// There is at most one decode plus one pending (latest) JPEG. A slow display
// drops preview frames instead of accumulating delayed frames. Scan data is untouched.
function queueFrame(bytes:Uint8Array,g:number){pending={bytes,g};if(!rendering)void paint()}
async function paint(){
 rendering=true
 try{while(pending){
  const item=pending;pending=null
  try{
   const bitmap=await createImageBitmap(new Blob([item.bytes as BlobPart],{type:'image/jpeg'}))
   try{if(current(item.g)&&canvas.value){
    if(bitmap.width!==1920||bitmap.height!==540)throw Error('Invalid paired preview')
    for(const [i,target] of [canvas.value,second.value].entries()){
     if(!target)continue
     if(target.width!==960||target.height!==540){target.width=960;target.height=540}
     const ctx=target.getContext('2d');if(!ctx)throw Error('No preview canvas')
     ctx.drawImage(bitmap,i*960,0,960,540,0,0,960,540)
    }
    waiting.value=false;failed.value=false
    lastFrame.value=new Date().toLocaleTimeString('zh-CN',{hour12:false});shown++
    const now=performance.now();if(now-windowStart>=1000){fps.value=(shown*1000/(now-windowStart)).toFixed(1);shown=0;windowStart=now}
   }}finally{bitmap.close()}
  }catch{if(current(item.g)){failed.value=true;controller?.abort()}}
 }}finally{rendering=false}
}
async function stream(g:number){
 if(!current(g))return
 mode.value='stream';const own=new AbortController();controller=own;let reader:ReadableStreamDefaultReader<Uint8Array>|undefined,lastReceived=performance.now()
 const watchdog=setInterval(()=>{if(performance.now()-lastReceived>3500)own.abort()},500)
 try{
  const response=await fetch('/api/scan3d/color-preview/pair.mjpeg',{cache:'no-store',signal:own.signal})
  if(!response.ok||!response.body)throw Error('Preview unavailable')
  reader=response.body.getReader();const parser=new MjpegParser()
  while(current(g)){
   const {value,done}=await reader.read();if(done)throw Error('Preview ended')
   for(const frame of parser.push(value)){lastReceived=performance.now();if(current(g))queueFrame(frame,g)}
  }
 }catch{if(current(g)){failed.value=true;void fallback(g,performance.now()+5000)}}
 finally{clearInterval(watchdog);try{await reader?.cancel()}catch{};reader?.releaseLock();if(controller===own)controller=undefined}
}
async function fallback(g:number,retryAt:number){
 if(!current(g))return
 mode.value='fallback';const own=new AbortController();controller=own;const timeout=setTimeout(()=>own.abort(),3000)
 try{
  const response=await fetch('/api/scan3d/color-preview/pair.jpg?t='+Date.now(),{cache:'no-store',signal:own.signal})
  if(!response.ok)throw Error('No JPEG');const bytes=new Uint8Array(await response.arrayBuffer());if(current(g))queueFrame(bytes,g)
 }catch{if(current(g))failed.value=true}
 finally{clearTimeout(timeout);if(controller===own)controller=undefined
  if(current(g))timer=setTimeout(()=>performance.now()>=retryAt?void stream(g):void fallback(g,retryAt),200)
 }
}
function connect(){
 generation++;controller?.abort();clearTimeout(timer);pending=null
 visible.value=!disposed&&!document.hidden&&onscreen
 if(visible.value){waiting.value=true;failed.value=false;fps.value='—';shown=0;windowStart=performance.now();void stream(generation)}
}
function resize(){const r=host.value?.getBoundingClientRect();if(r){height.value=Math.max(0,Math.min(r.height,r.width*16/9));width.value=height.value*9/16}}
watch(()=>props.streamId,(next,previous)=>{if(next&&next!==previous)connect()})
onMounted(()=>{
 void fetch('/api/scan3d/color-preview/status',{cache:'no-store'}).then(r=>r.json()).then(p=>profile.value=p).catch(()=>{})
 resize();observer=new ResizeObserver(resize);observer.observe(host.value!)
 intersection=new IntersectionObserver(entries=>{const shown=entries[0].isIntersecting;if(shown!==onscreen){onscreen=shown;connect()}})
 intersection.observe(host.value!);document.addEventListener('visibilitychange',connect);connect()
})
onBeforeUnmount(()=>{disposed=true;generation++;controller?.abort();clearTimeout(timer);pending=null;document.removeEventListener('visibilitychange',connect);observer?.disconnect();intersection?.disconnect();visible.value=false})
</script>
<style scoped>
.paired-camera{position:relative;width:100%;height:100%;display:flex;align-items:center;justify-content:center;overflow:hidden}
.paired-frame{position:relative;flex:none}
.paired-frame canvas{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%) rotate(90deg);max-width:none;aspect-ratio:auto;object-fit:contain}
.paired-badge{position:absolute;left:10px;bottom:10px;color:#fff;background:var(--ui-dark-overlay,#414849ed);padding:5px 8px;border-radius:5px;font-size:11px}
.panel-foot{font-size:11px}
</style>

<style scoped>
.scan-roi{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
</style>
