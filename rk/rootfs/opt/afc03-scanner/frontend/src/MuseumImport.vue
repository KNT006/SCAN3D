<template>
 <button class="museum-import-button" :disabled="!task||disabled" @click="open=true;error='';name=initialName">导入陈列馆</button>
 <Teleport to="body"><div v-if="open" class="museum-import-backdrop"><section class="museum-import-dialog" role="dialog" aria-modal="true" aria-label="导入陈列馆">
  <h2>放入陈列馆</h2><label>展品名称<input v-model="name" maxlength="32" :disabled="busy"/></label>
  <label>初始配色<select v-model="mode" :disabled="busy"><option value="cloud">按点云颜色分区</option><option value="plain">素色，自由上色</option></select></label>
  <p>导入当前选中的 STL，展品保存在 RK 陈列馆。</p>
  <p v-if="error" class="import-error" role="alert">{{error}}</p><p v-if="busy" role="status">{{progress}}</p>
  <div class="import-actions"><button :disabled="busy" @click="open=false">取消</button><button :disabled="busy||!name.trim()" @click="start">{{busy?'正在导入…':'导入并查看'}}</button></div>
  <iframe v-if="busy" ref="bridge" :src="museumOrigin+'/?import=1'" title="陈列馆导入通道" class="import-bridge"/>
 </section></div></Teleport>
</template>
<script setup lang="ts">
import {ref,onMounted,onBeforeUnmount} from 'vue'
import {parseResultCloud} from './cloudBinary'
const props=defineProps<{task:string,run:string,initialName:string,disabled?:boolean}>()
const emit=defineEmits<{imported:[id:string]}>()
const open=ref(false),name=ref(''),mode=ref('cloud'),busy=ref(false),error=ref(''),progress=ref(''),bridge=ref<HTMLIFrameElement>()
const host=location.port==='8834'?'192.168.1.89':location.hostname,museumOrigin=`${location.protocol}//${host}:8830`
let controller:AbortController|undefined,payload:any,ready=false,sent=false,requestId='',timer:any,disposed=false
function send(){if(ready&&payload&&!sent&&bridge.value?.contentWindow){sent=true;progress.value='正在分区上色并保存展品…';bridge.value.contentWindow.postMessage({type:'scan3d:import',requestId,payload},museumOrigin,[payload.stl,...(payload.xyz?[payload.xyz,payload.rgb]:[])]);payload=null;}}
function receive(e:MessageEvent){if(e.origin!==museumOrigin||e.source!==bridge.value?.contentWindow)return;if(e.data?.type==='scan3d:import-ready'){ready=true;send();}if(e.data?.requestId!==requestId)return;if(e.data?.type==='scan3d:import-result'){clearTimeout(timer);busy.value=false;if(e.data.error)error.value=e.data.error;else{open.value=false;emit('imported',e.data.id);}}}
async function bytes(url:string,max:number){const r=await fetch(url,{signal:controller!.signal});if(!r.ok)throw Error('扫描文件读取失败，请重新选择模型');if(Number(r.headers.get('content-length'))>max)throw Error('扫描文件过大，请选择较小的模型');const b=await r.arrayBuffer();if(b.byteLength>max)throw Error('扫描文件过大，请选择较小的模型');return b;}
async function start(){
 if(busy.value||!props.task)return;busy.value=true;error.value='';ready=false;sent=false;payload=null;controller=new AbortController();requestId=Date.now()+'-'+Math.random().toString(36).slice(2);progress.value='正在读取所选 STL…';
 const source={run:props.run,task:props.task,name:name.value.trim(),mode:mode.value};
 timer=setTimeout(()=>{controller?.abort();busy.value=false;error.value='导入等待超时，可重新尝试；已保存的展品可在陈列馆查看。';},180000);
 try{
  const stl=await bytes(`/api/scan3d/mesh-tasks/${encodeURIComponent(source.task)}/files/stl`,24*1024*1024);
  let xyz:ArrayBuffer|undefined,rgb:ArrayBuffer|undefined;
  if(source.mode==='cloud'){
   progress.value='正在读取点云颜色…';const cloud=parseResultCloud(await bytes(`/api/scan3d/runs/${encodeURIComponent(source.run)}/cloud.bin`,160*1024*1024));
   if(!cloud.count)throw Error('此扫描没有彩色点云，请改用素色导入');
   const step=Math.max(1,Math.ceil(cloud.count/100000)),count=Math.ceil(cloud.count/step),x=new Float32Array(count*3),c=new Uint8Array(count*3);
   for(let i=0,j=0;i<cloud.count;i+=step,j++){x.set(cloud.xyz.subarray(i*3,i*3+3),j*3);c.set(cloud.rgb.subarray(i*3,i*3+3),j*3);}xyz=x.buffer;rgb=c.buffer;
  }
  if(disposed||!busy.value)return;payload={...source,stl,xyz,rgb};send();
 }catch(e:any){clearTimeout(timer);if(!disposed){busy.value=false;error.value=e.name==='AbortError'?'导入已中断，请重试':/[\u4e00-\u9fff]/.test(e.message||'')?e.message:'扫描文件读取失败，请检查连接后重试';}}
}
onMounted(()=>window.addEventListener('message',receive))
onBeforeUnmount(()=>{disposed=true;controller?.abort();clearTimeout(timer);window.removeEventListener('message',receive)})
</script>
<style scoped>
.museum-import-button{white-space:nowrap}.museum-import-backdrop{position:fixed;inset:0;background:#26382f55;display:grid;place-items:center;z-index:90;font-family:'SCAN3D Marker',sans-serif;color:#283e3a}.museum-import-dialog{width:430px;max-width:90vw;padding:28px;background:#fffefa;border:1px solid #aec7c2;border-radius:16px;box-shadow:0 20px 60px #24382e22}.museum-import-dialog h2{font-size:26px;margin:0 0 22px}.museum-import-dialog label{display:flex;flex-direction:column;gap:8px;margin:16px 0}.museum-import-dialog input,.museum-import-dialog select{font:inherit;padding:10px;border:1px solid #b8cfca;border-radius:8px;background:#fffefa;color:inherit}.museum-import-dialog p{font-size:13px;line-height:1.8}.import-actions{display:flex;justify-content:flex-end;gap:12px;margin-top:24px}.import-actions button{font:inherit;border:1px solid #b8cfca;border-radius:30px;padding:10px 18px;background:#fffefa;color:#1c5d5f;cursor:pointer}.import-actions button:last-child{background:#1c5d5f;color:#fff}.import-actions button:disabled{opacity:.5;cursor:wait}.import-error{color:#984c42}.import-bridge{position:absolute;width:1px;height:1px;opacity:0;border:0;pointer-events:none}
</style>
