<template>
  <div class="viewer" ref="host" aria-label="可旋转的三维点云，拖动旋转，滚轮缩放">
    <div class="viewer-label"><span class="live-dot"></span>{{realColor?'实拍颜色':'扫描角度着色'}} · 点云预览</div>
    <div class="viewer-help">拖动旋转 · 滚轮缩放 <button @click="reset">复位视角</button></div>
    <div class="viewer-error" v-if="error">{{error}}</div>
    <div class="viewer-loading" v-if="loading">正在载入三维数据…</div>
  </div>
</template>
<script setup lang="ts">
import {ref,onMounted,onBeforeUnmount,watch} from 'vue'
import * as THREE from 'three'
import {OrbitControls} from 'three/addons/controls/OrbitControls.js'
const props=withDefaults(defineProps<{dataset:string,collection?:string}>(),{collection:'datasets'})
const host=ref<HTMLDivElement>(),error=ref(''),loading=ref(false),realColor=ref(false)
let renderer:THREE.WebGLRenderer,scene:THREE.Scene,camera:THREE.PerspectiveCamera,controls:OrbitControls,cloud:THREE.Points|undefined,observer:ResizeObserver,frame=0,requestId=0
let extent=75
let intersection:IntersectionObserver,onscreen=false
function render(){
 if(frame||!renderer||!onscreen||document.hidden)return
 frame=requestAnimationFrame(()=>{frame=0;renderer.render(scene,camera)})
}
function visibility(){if(document.hidden){cancelAnimationFrame(frame);frame=0}else render()}
function reset(){if(!camera)return;camera.position.set(extent*.95,extent*.62,extent*1.35);controls.target.set(0,0,0);controls.update()}
async function load(){
 if(!scene||!props.dataset)return
 const id=++requestId;loading.value=true;error.value=''
 try{
  const response=await fetch(`/api/${props.collection}/${props.dataset}/preview`);if(!response.ok)throw Error('三维数据暂不可用')
  const data=await response.json();if(id!==requestId)return
  realColor.value=data.real_color
  if(cloud){scene.remove(cloud);cloud.geometry.dispose();(cloud.material as THREE.Material).dispose()}
  const geometry=new THREE.BufferGeometry();const positions=new Float32Array(data.positions)
  geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));geometry.computeBoundingBox();geometry.center()
  const size=new THREE.Vector3();geometry.boundingBox!.getSize(size);extent=Math.max(size.x,size.y,size.z)
  const colors=new Float32Array(data.colors.length),color=new THREE.Color()
  for(let i=0;i<data.colors.length;i+=3){color.setRGB(data.colors[i]/255,data.colors[i+1]/255,data.colors[i+2]/255,THREE.SRGBColorSpace);colors[i]=color.r;colors[i+1]=color.g;colors[i+2]=color.b}
  geometry.setAttribute('color',new THREE.BufferAttribute(colors,3))
  cloud=new THREE.Points(geometry,new THREE.PointsMaterial({size:1.8,sizeAttenuation:false,vertexColors:true}));scene.add(cloud);reset()
 }catch(e:any){error.value=e.message}finally{if(id===requestId)loading.value=false}
}
onMounted(()=>{
 try{
  scene=new THREE.Scene();scene.background=new THREE.Color('#edf2ef');camera=new THREE.PerspectiveCamera(40,1,.1,3000)
  renderer=new THREE.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(window.devicePixelRatio,2));host.value!.prepend(renderer.domElement)
  controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=false;controls.addEventListener('change',render)
  const grid=new THREE.GridHelper(140,14,0xb6c9c3,0xd5dfda);grid.position.y=-38;scene.add(grid)
  observer=new ResizeObserver(()=>{const {clientWidth:w,clientHeight:h}=host.value!;if(!w||!h)return;renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();render()});observer.observe(host.value!)
  intersection=new IntersectionObserver(entries=>{onscreen=entries[0].isIntersecting;if(onscreen)render();else{cancelAnimationFrame(frame);frame=0}});intersection.observe(host.value!)
  document.addEventListener('visibilitychange',visibility);load()
 }catch{error.value='当前浏览器无法启用三维显示，请使用支持 WebGL 的浏览器。'}
})
watch(()=>props.dataset,load)
onBeforeUnmount(()=>{requestId++;cancelAnimationFrame(frame);document.removeEventListener('visibilitychange',visibility);intersection?.disconnect();observer?.disconnect();controls?.dispose();cloud?.geometry.dispose();if(cloud)(cloud.material as THREE.Material).dispose();renderer?.dispose()})
</script>
