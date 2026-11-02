<script setup lang="ts">
import {computed,onMounted,onBeforeUnmount,ref,watch} from 'vue';
import type {ExhibitAsset,ExhibitRecord} from './MuseumData';
import {renderCabinetPreviews} from './CabinetPreviews';
import './cabinet.css';
const props=defineProps<{assets:ExhibitAsset[];records:Record<string,ExhibitRecord>;disabled:boolean}>();
const emit=defineEmits<{open:[id:string]}>();
const PAGE_SIZE=12;
const page=ref(0),previews=ref<Record<string,string>>({});
const pages=computed(()=>Math.max(1,Math.ceil(props.assets.length/PAGE_SIZE)));
const slots=computed(()=>Array.from({length:PAGE_SIZE},(_,i)=>props.assets[page.value*PAGE_SIZE+i]));
const room=ref<HTMLElement>();
let motion:MediaQueryList|undefined;
function look(e:PointerEvent){
 if(!room.value||e.pointerType==='touch'||motion?.matches)return;
 const r=room.value.getBoundingClientRect(),x=(e.clientX-r.left)/r.width-.5,y=(e.clientY-r.top)/r.height-.5;
 room.value.style.setProperty('--look-x',`${x*1.8}deg`);
 room.value.style.setProperty('--look-y',`${-y*1.2}deg`);
 room.value.style.setProperty('--light-x',`${50+x*12}%`);
}
function rest(){room.value?.style.setProperty('--look-x','0deg');room.value?.style.setProperty('--look-y','0deg');}
let abort:AbortController|undefined;
function paintSaved(){void prepare();}
async function prepare(){
 abort?.abort();if(props.disabled)return;const current=new AbortController();abort=current;
 for(const url of Object.values(previews.value))URL.revokeObjectURL(url);previews.value={};
 const visible=slots.value.filter((a):a is ExhibitAsset=>!!a);
 try{await renderCabinetPreviews(visible,props.records,current.signal,(id,url)=>{
  if(current.signal.aborted){URL.revokeObjectURL(url);return;}
  if(previews.value[id])URL.revokeObjectURL(previews.value[id]);previews.value[id]=url;
 });}catch(e){console.warn('Cabinet uses static mesh previews',e);}
}
watch(page,prepare);
watch(()=>props.disabled,value=>{if(value)abort?.abort();else void prepare();});
watch(()=>props.assets.map(a=>a.id).join(','),()=>{if(page.value>=pages.value)page.value=pages.value-1;else void prepare();});
onMounted(()=>{window.addEventListener('scan3d-paint-saved',paintSaved);motion=window.matchMedia('(prefers-reduced-motion: reduce)');void prepare();});
onBeforeUnmount(()=>{window.removeEventListener('scan3d-paint-saved',paintSaved);abort?.abort();Object.values(previews.value).forEach(URL.revokeObjectURL);});
</script>

<template>
<main ref="room" class="cabinet-gallery" aria-label="扫描物品陈列柜" @pointermove="look" @pointerleave="rest">
 <div class="gallery-architecture" aria-hidden="true"><i></i><i></i><i></i><span class="gallery-floor"></span></div>
 <div class="cabinet-area">
  <section class="wood-cabinet" aria-label="展品架">
   <div class="cabinet-crown" aria-hidden="true"><svg viewBox="0 0 1200 95" preserveAspectRatio="none"><defs><linearGradient id="crown-wood" x2="0" y2="1"><stop stop-color="#a87a51"/><stop offset=".5" stop-color="#875634"/><stop offset="1" stop-color="#63402b"/></linearGradient></defs><path d="M3 91V46H245Q600 -34 955 46H1197V91Z" fill="url(#crown-wood)" stroke="#bd9670" stroke-width="2"/><path d="M16 62H247Q600 -13 953 62H1184" fill="none" stroke="#d4ac76" stroke-opacity=".48"/><path d="M530 42Q558 46 580 54M620 54Q642 46 670 42M564 36Q578 38 590 52M610 52Q622 38 636 36" stroke="#d2b389" stroke-opacity=".55" fill="none" stroke-width="1.6"/><path d="M600 26L606 38L600 50L594 38Z" fill="#dbc190" opacity=".65"/></svg></div>
   <div class="cabinet-frame">
    <div class="cabinet-shelves">
     <template v-for="(a,i) in slots" :key="page*PAGE_SIZE+i">
      <button v-if="a" class="cabinet-slot" :disabled="disabled" :aria-label="'查看'+(records[a.id]?.name||a.name)+' · '+a.category" @click="emit('open',a.id)">
       <span class="niche-back" aria-hidden="true"></span><span class="niche-side side-left" aria-hidden="true"></span><span class="niche-side side-right" aria-hidden="true"></span><span class="niche-ceiling" aria-hidden="true"></span><span class="niche-floor" aria-hidden="true"></span>
       <span class="cabinet-lamp" aria-hidden="true"></span><span class="cabinet-beam" aria-hidden="true"></span>
       <span class="display-plinth" aria-hidden="true"><i></i></span>
       <span class="cabinet-object"><span class="object-halo" aria-hidden="true"></span><img :src="previews[a.id]||a.thumbnail" alt="" draggable="false"></span>
       <span class="cabinet-glint" aria-hidden="true"></span><span class="visit-arrow" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M6 18 18 6M6 6h12v12"/></svg></span>
      </button>
      <div v-else class="cabinet-slot empty-slot" aria-hidden="true"><span class="niche-back"></span><span class="niche-side side-left"></span><span class="niche-side side-right"></span><span class="niche-ceiling"></span><span class="niche-floor"></span><span class="cabinet-lamp"></span><span class="cabinet-beam"></span></div>
     </template>
    </div>
   </div>
   <div class="cabinet-base" aria-hidden="true"></div>
   <div class="cabinet-feet" aria-hidden="true"></div>
  </section>
 </div>
 <nav class="cabinet-pages" aria-label="陈列柜分页"><button :disabled="page===0" @click="page--" aria-label="上一页"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m14 6-6 6 6 6"/></svg></button><span class="cabinet-page-number" aria-live="polite">{{page+1}} / {{pages}}</span><button :disabled="page===pages-1" @click="page++" aria-label="下一页"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m10 6 6 6-6 6"/></svg></button></nav>
</main>
</template>
