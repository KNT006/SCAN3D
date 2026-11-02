<script setup lang="ts">
import {ref,onMounted,onBeforeUnmount,watch} from 'vue';
import {ExhibitScene} from './ExhibitScene';import type {ExhibitAsset} from './MuseumData';
const props=defineProps<{asset:ExhibitAsset;yaw:number}>();const emit=defineEmits(['ready','notice','selected','sampled']);
const host=ref<HTMLDivElement>(),error=ref(''),ready=ref(false),fps=ref(0),ms=ref(0);let scene:ExhibitScene,timer:any;
async function start(){try{scene=new ExhibitScene(host.value!,props.asset,s=>emit('notice',s),n=>emit('selected',n),()=>emit('ready',scene));scene.sampled=c=>emit('sampled',c);await scene.load();if(scene.disposed)return;scene.setYaw(props.yaw);ready.value=true;ms.value=scene.loadMs;emit('ready',scene);timer=setInterval(()=>fps.value=scene.fps,1000);}catch(e:any){if(e.name!=='AbortError')error.value=e.message;}}
function retry(){scene?.dispose();error.value='';void start();}
watch(()=>props.yaw,v=>scene?.setYaw(v));onMounted(start);onBeforeUnmount(()=>{clearInterval(timer);scene?.dispose();});
</script>
<template><div ref="host" class="exhibit-canvas"></div><div v-if="!ready&&!error" class="model-message">正在迎接这件展品…</div><div v-if="error" class="model-message">{{error}}<button @click="retry">重新加载</button></div></template>
