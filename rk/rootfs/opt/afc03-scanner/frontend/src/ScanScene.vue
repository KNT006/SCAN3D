<template><div ref="host" class="scene" :class="{'dark-scene':dark}"><span class="scene-label">{{stl?'STL 表面':binary?`${binary.count.toLocaleString()} 个点　完整点云`:`${(preview?preview.count:points.length).toLocaleString()} 个预览点`}}</span><button class="scene-reset" @click="reset">复位视角</button><span class="scene-error" v-if="error||loadError">{{errorZh(error||loadError)}}</span><span class="cloud-loading" v-else-if="loading||waiting">{{loading?'正在载入完整点云，完成后整体显示…':waiting}}</span><button class="scene-theme" @click="toggleTheme">{{dark?'浅色背景':'深色背景'}}</button></div></template>
<script setup lang="ts">
import {errorZh} from './errorZh'
import {ref,onMounted,onBeforeUnmount,watch} from 'vue'
import * as T from 'three'
import {OrbitControls} from 'three/addons/controls/OrbitControls.js'
import {STLLoader} from 'three/addons/loaders/STLLoader.js'
import type {PreviewBuffer} from './previewBuffer'
import type {ResultCloud} from './cloudBinary'
const props=withDefaults(defineProps<{preview?:PreviewBuffer,previewRevision?:number,points?:number[][],colors?:number[][],stl?:string,binary?:ResultCloud|null,loading?:boolean,loadError?:string,waiting?:string}>(),{points:()=>[],colors:()=>[],stl:'',binary:null,loading:false,loadError:'',waiting:''})
const colorLut=Float32Array.from({length:256},(_,i)=>new T.Color().setRGB(i/255,i/255,i/255,T.SRGBColorSpace).r)
const host=ref<HTMLElement>(),error=ref(''),dark=ref(false);let manualTheme=false;let renderer:T.WebGLRenderer,scene:T.Scene,camera:T.PerspectiveCamera,controls:OrbitControls,object:T.Points|T.Mesh|undefined,observer:ResizeObserver,extent=100,frame=0,token=0,initialized=false,center=new T.Vector3()
function draw(){if(!renderer||frame||document.hidden)return;frame=requestAnimationFrame(()=>{frame=0;renderer.render(scene,camera)})}
function applyBackground(){if(!scene)return;const darkBackground=host.value?getComputedStyle(host.value).getPropertyValue('--ui-dark-bg').trim():'';scene.background=new T.Color(dark.value?(darkBackground||'#414849'):'#efefe9');draw()}
function toggleTheme(){manualTheme=true;dark.value=!dark.value;if(!props.stl&&!props.colors.length&&!props.binary)update();else applyBackground()}
function reset(){if(!camera)return;camera.position.set(center.x+extent,center.y+extent*.6,center.z+extent*1.3);controls.target.copy(center);controls.update();draw()}
function clear(){if(object){scene.remove(object);object.geometry.dispose();(object.material as T.Material).dispose();object=undefined}}
let previewSource:PreviewBuffer|undefined,previewUploaded=0
function updatePreview(){
 if(!scene||!props.preview)return
 const start=performance.now(),source=props.preview
 if(source!==previewSource||!object){
  clear();previewSource=source;previewUploaded=0
  const g=new T.BufferGeometry()
  g.setAttribute('position',new T.BufferAttribute(source.xyz,3).setUsage(T.DynamicDrawUsage))
  g.setAttribute('color',new T.BufferAttribute(new Float32Array(source.xyz.length),3).setUsage(T.DynamicDrawUsage))
  object=new T.Points(g,new T.PointsMaterial({size:2,sizeAttenuation:false,vertexColors:true}));object.frustumCulled=false;scene.add(object)
 }
 const g=object!.geometry,pos=g.getAttribute('position') as T.BufferAttribute,col=g.getAttribute('color') as T.BufferAttribute
 const from=previewUploaded*3,to=source.count*3
 for(let i=from;i<to;i++)col.array[i]=colorLut[source.rgb[i]]
 if(to>from){pos.addUpdateRange(from,to-from);col.addUpdateRange(from,to-from);pos.needsUpdate=true;col.needsUpdate=true}
 g.setDrawRange(0,source.count);previewUploaded=source.count
 if(!manualTheme)dark.value=true;applyBackground()
 if(!initialized&&source.count){const box=new T.Box3();for(let i=0;i<to;i+=3)box.expandByPoint(new T.Vector3(source.xyz[i],source.xyz[i+1],source.xyz[i+2]));box.getCenter(center);extent=Math.max(...box.getSize(new T.Vector3()).toArray(),20);reset();initialized=true}
 draw();if(to>from)console.debug('scan3d-preview-render',JSON.stringify({added:(to-from)/3,count:source.count,updateMs:performance.now()-start,bufferBytes:source.xyz.byteLength+source.rgb.byteLength+col.array.byteLength}))
}
watch(()=>[props.preview,props.previewRevision],updatePreview)
async function update(){if(!scene)return;if(props.preview){updatePreview();return;}const id=++token;error.value='';if(!manualTheme)dark.value=!props.stl&&(props.colors.length>0||!!props.binary);applyBackground();try{let g:T.BufferGeometry,material:T.Material
 if(props.stl){const r=await fetch(props.stl);if(!r.ok)throw Error('STL 载入失败');g=new STLLoader().parse(await r.arrayBuffer());material=new T.MeshStandardMaterial({color:0xe5e4dc,roughness:.7,side:T.DoubleSide})}
 else if(props.binary){g=new T.BufferGeometry();g.setAttribute('position',new T.BufferAttribute(props.binary.xyz,3));const rgb=props.binary.rgb,linear=new Float32Array(rgb.length);for(let i=0;i<rgb.length;i++)linear[i]=colorLut[rgb[i]];g.setAttribute('color',new T.BufferAttribute(linear,3));material=new T.PointsMaterial({size:2,sizeAttenuation:false,vertexColors:true})}
 else{g=new T.BufferGeometry();g.setAttribute('position',new T.Float32BufferAttribute(props.points.flat(),3));const colors:number[]=[];const c=new T.Color();for(let i=0;i<props.points.length;i++){const rgb=props.colors[i]||(dark.value?[226,227,216]:[65,69,63]);c.setRGB(rgb[0]/255,rgb[1]/255,rgb[2]/255,T.SRGBColorSpace);colors.push(c.r,c.g,c.b)}g.setAttribute('color',new T.Float32BufferAttribute(colors,3));material=new T.PointsMaterial({size:2,sizeAttenuation:false,vertexColors:true})}
 if(id!==token){g.dispose();material.dispose();return}clear();object=props.stl?new T.Mesh(g,material):new T.Points(g,material);scene.add(object);g.computeBoundingBox();if(g.boundingBox&&!g.boundingBox.isEmpty()){g.boundingBox.getCenter(center);extent=Math.max(...g.boundingBox.getSize(new T.Vector3()).toArray(),20);if(!initialized){reset();initialized=true}}draw()
 }catch(e:any){error.value=errorZh(e)}}
watch(()=>[props.points,props.colors,props.stl,props.binary],update)
// A completed replay may receive no more chunks after a hidden tab returns.
// Flush its pending GPU ranges without resetting the user's camera.
onMounted(()=>document.addEventListener('visibilitychange',draw))
onBeforeUnmount(()=>document.removeEventListener('visibilitychange',draw))
onMounted(()=>{try{scene=new T.Scene();scene.background=new T.Color('#efefe9');camera=new T.PerspectiveCamera(40,1,.01,10000);renderer=new T.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));host.value!.prepend(renderer.domElement);controls=new OrbitControls(camera,renderer.domElement);controls.addEventListener('change',draw);scene.add(new T.HemisphereLight(0xffffff,0x858579,2));const light=new T.DirectionalLight(0xffffff,3);light.position.set(50,100,70);scene.add(light);scene.add(new T.AxesHelper(25));observer=new ResizeObserver(()=>{const w=host.value!.clientWidth,h=host.value!.clientHeight;if(w&&h){renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();draw()}});observer.observe(host.value!);update()}catch{error.value='WebGL 不可用，请启用浏览器硬件加速'}})
onBeforeUnmount(()=>{token++;cancelAnimationFrame(frame);observer?.disconnect();controls?.dispose();clear();renderer?.dispose()})
</script>
<style scoped>.cloud-loading{position:absolute;inset:0;display:grid;place-items:center;padding:32px;text-align:center;background:rgba(239,239,233,.9);color:#3e413b;font-size:15px;z-index:2}</style>
