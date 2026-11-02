import {createApp,h,ref,onMounted,onBeforeUnmount} from 'vue'
import ScanScene from '../src/ScanScene.vue'
import {useScanMonitor} from '../src/useScanMonitor.ts'
createApp({setup(){
 const visible=ref(true),tick=ref(0)
 const m=useScanMonitor(async(path)=>{
  if(path.endsWith('/state'))return {id:'fixture',status:'complete',completed_positions:3201}
  const u=new URL(path,'http://test'),after=Number(u.searchParams.get('after')),chunks=[]
  for(let i=after+1;i<Math.min(after+9,3200);i++){
   const angle=i*Math.PI*2/3200,xyz=[],rgb=[]
   for(let j=0;j<50;j++){xyz.push([30*Math.cos(angle),j-25,30*Math.sin(angle)]);rgb.push([i%256,j*5,200])}
   chunks.push({index:i,xyz,rgb})
  }
  return {id:'fixture',protocol:2,chunks,gaps:[],cursor:chunks.at(-1)?.index??after,available_through:3199}
 })
 let timer:any
 onMounted(()=>{m.bind('fixture');timer=setInterval(async()=>{await m.refreshPoints();tick.value++},20)})
 onBeforeUnmount(()=>{clearInterval(timer);m.dispose()})
 return ()=>h('main',[h('h1','3200 位置预览回归'),h('p',`位置 ${m.preview.value.seen.size} / 3200 · 点数 ${m.preview.value.count} · 最后位置 ${Math.max(-1,...m.preview.value.seen)} · 更新 ${tick.value}`),h('button',{onClick:()=>{visible.value=!visible.value;m.setEnabled(visible.value)}},visible.value?'离开预览':'重新进入'),visible.value?h(ScanScene,{preview:m.preview.value,previewRevision:m.revision.value}):null])
}}).mount('#app')
