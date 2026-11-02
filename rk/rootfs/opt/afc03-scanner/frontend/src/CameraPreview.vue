<template>
 <div class="live-camera" ref="host">
  <div class="live-camera-frame" :style="{width:width+'px',height:height+'px'}">
   <canvas ref="canvas" :style="{width:height+'px',height:width+'px'}" aria-label="实时相机画面"/>
   <slot/>
  </div>
  <p v-if="waiting||failed" class="live-camera-message" role="status">{{failed?'预览连接中断，正在恢复…':'正在连接相机…'}}</p>
  <span v-else class="live-camera-badge">{{mode==='stream'?'连续预览':'恢复中　JPEG 备用'}}　{{fps}} fps　{{lastFrame}}</span>
 </div>
</template>
<script setup lang="ts">
import {ref,watch,onMounted,onBeforeUnmount} from 'vue'
import {MjpegParser} from './mjpeg'
const props=defineProps<{streamId?:string}>()
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
    const target=canvas.value
    if(target.width!==bitmap.width||target.height!==bitmap.height){target.width=bitmap.width;target.height=bitmap.height}
    const ctx=target.getContext('2d');if(!ctx)throw Error('No preview canvas')
    ctx.drawImage(bitmap,0,0);waiting.value=false;failed.value=false
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
  const response=await fetch('/api/scan3d/preview.mjpeg',{cache:'no-store',signal:own.signal})
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
  const response=await fetch('/api/scan3d/preview.jpg?t='+Date.now(),{cache:'no-store',signal:own.signal})
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
 resize();observer=new ResizeObserver(resize);observer.observe(host.value!)
 intersection=new IntersectionObserver(entries=>{const shown=entries[0].isIntersecting;if(shown!==onscreen){onscreen=shown;connect()}})
 intersection.observe(host.value!);document.addEventListener('visibilitychange',connect);connect()
})
onBeforeUnmount(()=>{disposed=true;generation++;controller?.abort();clearTimeout(timer);pending=null;document.removeEventListener('visibilitychange',connect);observer?.disconnect();intersection?.disconnect();visible.value=false})
</script>
<style scoped>
.live-camera{position:relative;width:100%;height:100%;display:flex;align-items:center;justify-content:center;overflow:hidden}
.live-camera-frame{position:relative;flex:none}
.live-camera-frame canvas{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%) rotate(90deg);max-width:none;aspect-ratio:auto;object-fit:contain}
.live-camera-frame :deep(svg){position:absolute;inset:0;width:100%;height:100%;max-width:none;aspect-ratio:auto;pointer-events:none}
.live-camera-message{position:absolute;color:#fff;background:var(--ui-dark-overlay,#414849ed);padding:8px 12px;font-size:12px}
.live-camera-badge{position:absolute;left:10px;bottom:10px;color:#fff;background:var(--ui-dark-overlay,#414849ed);padding:4px 8px;border-radius:5px;font-size:11px}
</style>
