<script setup lang="ts">
import {ref,computed,onMounted,onBeforeUnmount,nextTick} from 'vue';
import ExhibitViewport from './ExhibitViewport.vue';
import CabinetGallery from './CabinetGallery.vue';
import {defaults,loadRecord,saveRecord,introduction,answerQuestion,validateRecord} from './MuseumData';
import type {ExhibitAsset,ExhibitRecord,Answer} from './MuseumData';
import type {ExhibitScene} from './ExhibitScene';
import {makeGLB,makeArchive,readArchive,downloadBlob} from './MuseumArchive';
import {askAI,getAIStatus} from './MuseumAI';
import {storePaint} from '../DuckPaint';
import {resolveSegmentation,paintKey} from './MuseumSegmentation';
import {clearLocalExhibit} from './MuseumDeletion';
import {BRUSHES} from '../BrushProfiles';
import type {BrushStyle} from '../BrushProfiles';
const brushStyle=ref<BrushStyle>('pen'),brushOpacity=ref(1);
function chooseBrush(id:BrushStyle){scene?.paint?.commit();brushStyle.value=id;radius.value=BRUSHES.find(b=>b.id===id)?.radius||3;setTool('brush');}
const catalogReady=ref(false),deleting=ref<ExhibitAsset|null>(null);
const catalog=ref<ExhibitAsset[]>([]),records=ref<Record<string,ExhibitRecord>>({}),activeId=ref('duck'),panel=ref('story'),fatal=ref(''),toast=ref(''),busy=ref(false),loaded=ref(false),selected=ref(0),palette=ref<string[]>([]),hex=ref(''),tool=ref('select'),brushColor=ref('#e895b3'),radius=ref(1.2),highlight=ref(false),neutral=ref(false),softEdges=ref(true),undoCount=ref(0),autoRotate=ref(false),showInfo=ref(false),query=ref(''),chatBody=ref<HTMLDivElement>(),speaking=ref(false),voiceAvailable=ref(false),pending=ref<Awaited<ReturnType<typeof readArchive>>|null>(null),draft=ref<any>({}),viewKey=ref(0);
const aiConfigured=ref(false),aiEnabled=ref(true),aiPending=ref(false),aiConnected=ref(false),aiError=ref('');
let aiRequest:AbortController|undefined;
async function refreshAI(){const status=await getAIStatus();aiConfigured.value=status.configured;aiError.value=status.error||'';}
function cancelAI(){aiRequest?.abort();aiRequest=undefined;aiPending.value=false;}
function toggleAI(){cancelAI();aiEnabled.value=!aiEnabled.value;aiConnected.value=false;}
const displayCatalog=computed(()=>catalog.value.map(a=>resolveSegmentation(a)));
const current=computed(()=>displayCatalog.value.find(a=>a.id===activeId.value)),record=computed(()=>records.value[activeId.value]),intro=computed(()=>current.value&&record.value?introduction(current.value,record.value):null);
const screen=ref<'cabinet'|'exhibit'>('cabinet');
const suggestions=['介绍一下自己','我们相遇多久了？','讲一个小故事'];
let scene:ExhibitScene|undefined,toastTimer:any;const abort=new AbortController();let destroyed=false;
function notice(s:string){toast.value=s;clearTimeout(toastTimer);toastTimer=setTimeout(()=>toast.value='',4200);}
function persist(){if(!current.value||!record.value)return;try{saveRecord(current.value,record.value);}catch{notice('本机保存失败，请导出展品包');}}
function fillDraft(){if(!record.value)return;draft.value={name:record.value.name,category:record.value.category,features:record.value.features.join('、'),story:record.value.story,acquiredDate:record.value.acquiredDate,acquiredPlace:record.value.acquiredPlace,tone:record.value.tone};}
const dirty=computed(()=>record.value&&(draft.value.name!==record.value.name||draft.value.category!==record.value.category||draft.value.features!==record.value.features.join('、')||draft.value.story!==record.value.story||draft.value.acquiredDate!==record.value.acquiredDate||draft.value.acquiredPlace!==record.value.acquiredPlace||draft.value.tone!==record.value.tone));
function saveDraft(announce=true){cancelAI();if(!current.value||!record.value)return;const r=record.value;if(draft.value.story!==r.story){r.versions.push({story:r.story,time:Date.now()});r.versions=r.versions.slice(-8);}const next=validateRecord(current.value,{...r,...draft.value,features:String(draft.value.features||'').split(/[、\n]/).filter(Boolean),updated:Date.now()});records.value[activeId.value]=next;fillDraft();persist();if(announce)notice('档案已保存，讲述内容已更新');}
function displayMessage(m:{role:string;text:string}){return m.role==='exhibit'?m.text.replace(/(?:^|\n)\s*天气(?:数据)?(?:来源)?[：:]\s*Open-Meteo\s*$/i,'').trimEnd():m.text;}
function rememberMessage(text:string){
 if(!record.value)return;
 if(dirty.value)saveDraft(false);
 const r=record.value;if(r.story.includes(text)){notice('这段话已在故事里');return;}
 const story=[r.story,text].filter(Boolean).join('\n');
 if(story.length>4000){notice('故事已接近4000字，请在档案中整理后保存');return;}
 draft.value.story=story;saveDraft(false);notice('已记入当前物品的故事，可在档案中修改');
}
function restoreStory(){const r=record.value;if(!r?.versions.length)return;const previous=r.versions.pop()!;r.story=previous.story;r.updated=Date.now();fillDraft();persist();notice('上一版故事已恢复');}
function reload(){window.location.reload();}
function rememberSelection(){try{localStorage.setItem('scan3d-museum-active',activeId.value);}catch{}}
function showExhibit(id:string){if(!catalog.value.some(a=>a.id===id))return;if(id===activeId.value&&screen.value==='exhibit')return;cancelAI();if(dirty.value)saveDraft(false);stopVoice();scene=undefined;loaded.value=false;activeId.value=id;screen.value='exhibit';rememberSelection();selected.value=0;tool.value='select';highlight.value=false;neutral.value=false;autoRotate.value=false;showInfo.value=false;fillDraft();query.value='';}
function selectExhibit(id:string){if(busy.value)return;const hash='#exhibit/'+encodeURIComponent(id);if(location.hash!==hash)history.pushState(null,'',hash);showExhibit(id);}
function showCabinet(){cancelAI();if(dirty.value)saveDraft(false);stopVoice();scene=undefined;loaded.value=false;autoRotate.value=false;showInfo.value=false;screen.value='cabinet';}
function goCabinet(){if(busy.value)return;if(location.hash)history.pushState(null,'',location.pathname+location.search);showCabinet();}
function readRoute(){let id='';try{if(location.hash.startsWith('#exhibit/'))id=decodeURIComponent(location.hash.slice(9));}catch{}if(catalog.value.some(a=>a.id===id))showExhibit(id);else showCabinet();}
function ready(s:ExhibitScene){if(s.asset.id!==activeId.value||screen.value!=='exhibit'||paintKey(s.asset)!==paintKey(current.value!))return;scene=s;loaded.value=s.ready;softEdges.value=s.paint?.softEdges??true;palette.value=[...(s.paint?.palette||[])];hex.value=palette.value[selected.value];undoCount.value=s.paint?.history.length||0;syncScene();}
function pick(n:number){selected.value=n;hex.value=palette.value[n];syncScene();}
function syncScene(){if(!scene)return;scene.editing=panel.value==='paint';scene.tool=tool.value;scene.selected=selected.value;scene.radius=radius.value;scene.brushColor=brushColor.value;scene.brushStyle=brushStyle.value;scene.brushOpacity=brushOpacity.value;scene.highlight=highlight.value&&panel.value==='paint';scene.spin=autoRotate.value&&panel.value!=='paint';scene.setNeutral(neutral.value);scene.sync();}
function setSoftEdges(){if(!scene?.paint)return;scene.paint.softEdges=softEdges.value;scene.paint.refresh();scene.scheduleSave();}
function setPanel(v:string){panel.value=v;autoRotate.value=false;if(scene){scene.perform('none');scene.spin=false;}syncScene();}
function color(c:string){if(!scene||!/^#[0-9a-f]{6}$/i.test(c))return;hex.value=c;palette.value[selected.value]=c;scene.color(selected.value,c);neutral.value=false;syncScene();}
function preset(kind:string){if(!scene||!current.value)return;const a=current.value;let p=[...a.palette];if(kind==='porcelain')p=p.map(()=> '#c6dad5');if(kind==='clay')p=p.map(()=> '#bd8972');if(kind==='ivory')p=p.map(()=> '#e7dfd0');scene.preset(p);palette.value=p;hex.value=p[selected.value];neutral.value=false;syncScene();}
function undo(){if(scene?.paint?.undo()){undoCount.value=scene.paint.history.length;scene.scheduleSave();notice('已撤销上一笔');}}
function setTool(v:string){scene?.paint?.commit();tool.value=v;neutral.value=false;highlight.value=false;syncScene();}
function sampleColor(c:string){brushColor.value=c;setTool('brush');notice('已取色 '+c+'，可继续涂色');}
function brushHex(c:string){if(/^#[0-9a-f]{6}$/i.test(c)){brushColor.value=c;syncScene();}}
function clearPaint(){scene?.paint?.clearPaint();undoCount.value=scene?.paint?.history.length||0;scene?.scheduleSave();notice('已清除涂色，可撤销');}
async function send(q=query.value){
 if(!current.value||!q.trim()||aiPending.value)return;
 const a=current.value,r=record.value,text=q.trim().slice(0,500),controller=new AbortController();aiRequest=controller;aiPending.value=true;query.value='';
 // Snapshot before adding this question so the history does not duplicate it.
 const context={...r,messages:r.messages.slice()};r.messages.push({role:'user',text,time:Date.now()});persist();
 let reply:Answer;
 try{
  if(aiEnabled.value){reply=await askAI(a,context,text,controller.signal);aiConnected.value=true;aiError.value='';}
  else{reply=answerQuestion(a,r,text);reply.source='离线档案';}
 }catch(e:any){
  if(controller.signal.aborted)return;
  aiConnected.value=false;aiError.value=e.message||'AI 服务暂不可用';notice(aiError.value);return;
 }finally{if(aiRequest===controller){aiPending.value=false;aiRequest=undefined;}}
 if(controller.signal.aborted||destroyed||activeId.value!==a.id||screen.value!=='exhibit')return;
 r.messages.push({role:'exhibit',text:reply.text,source:reply.source,time:Date.now()});r.messages=r.messages.slice(-30);persist();scene?.perform(reply.action,reply.region);await nextTick();chatBody.value?.scrollTo({top:chatBody.value.scrollHeight,behavior:'smooth'});
}
function clearChat(){cancelAI();record.value.messages=[];persist();notice('本展品的对话记录已清空');}
function greet(){scene?.perform('nod');notice('谢谢你来看我。');}
function stopVoice(){if('speechSynthesis'in window)window.speechSynthesis.cancel();speaking.value=false;}
function speak(text:string){if(!voiceAvailable.value){notice('此浏览器没有语音朗读支持，文字功能可正常使用');return;}stopVoice();const u=new SpeechSynthesisUtterance(text);u.lang='zh-CN';const voices=speechSynthesis.getVoices();const localVoice=voices.find(v=>v.localService&&v.lang.startsWith('zh'));if(!localVoice){notice('未找到本机中文语音；安装系统中文语音包后可朗读，文字互动仍可用');return;}u.voice=localVoice;u.rate=.95;u.onend=()=>speaking.value=false;u.onerror=()=>{speaking.value=false;notice('语音未能播放，可继续阅读文字');};speaking.value=true;speechSynthesis.speak(u);}
function readCurrent(){if(speaking.value){stopVoice();return;}const messages=record.value.messages.filter(m=>m.role==='exhibit');speak(messages.at(-1)?.text||intro.value!.text);}
async function exportPackage(){if(!scene?.paint||!current.value||busy.value)return;if(dirty.value)saveDraft(false);const s=scene,a=current.value,r=JSON.parse(JSON.stringify(record.value));busy.value=true;try{const data=await makeArchive(a,r,s.paint!,s.buffers);downloadBlob(new Blob([data as BlobPart],{type:'application/zip'}),a.id+'-scan3d-exhibit.zip');notice('展品包已导出：彩色模型、故事、配色和分区');}catch(e:any){notice('导出失败：'+e.message);}finally{busy.value=false;}}
async function exportModel(){if(!scene?.paint||!current.value||busy.value)return;const s=scene,a=current.value;busy.value=true;try{const glb=await makeGLB(a,s.paint!);downloadBlob(new Blob([glb],{type:'model/gltf-binary'}),a.id+'-museum.glb');notice('已导出可独立打开的彩色 GLB');}catch(e:any){notice('导出失败：'+e.message);}finally{busy.value=false;}}
async function screenshot(){if(!scene)return;try{downloadBlob(await scene.screenshot(),activeId.value+'-exhibit.png');notice('三维展品图片已导出');}catch(e:any){notice(e.message);}}
async function importPackage(e:Event){const input=e.target as HTMLInputElement;try{const f=input.files?.[0];if(f)pending.value=await readArchive(f,catalog.value);}catch(e:any){notice('不能导入：'+e.message);}input.value='';}
async function applyImport(){cancelAI();const p=pending.value;if(!p)return;busy.value=true;try{const paintData={labels:p.paint.labels.slice(),palette:[...p.paint.palette],softEdges:p.paint.softEdges,faceColors:p.paint.faceColors.slice(),surface:p.paint.surface.slice(),round:p.paint.round?.slice()};if(scene&&paintKey(scene.asset)===paintKey(p.asset)){clearTimeout(scene.saveTimer);scene.paint?.restore(paintData);}await storePaint(paintKey(p.asset),paintData);saveRecord(p.asset,p.record);records.value[p.asset.id]=p.record;stopVoice();scene=undefined;loaded.value=false;activeId.value=p.asset.id;screen.value='exhibit';history.pushState(null,'','#exhibit/'+encodeURIComponent(p.asset.id));rememberSelection();viewKey.value++;selected.value=0;highlight.value=false;neutral.value=false;autoRotate.value=false;fillDraft();pending.value=null;notice('展品档案与配色已恢复');}catch(e:any){notice('导入保存失败：'+e.message);}finally{busy.value=false;}}
function requestDelete(id:string){if(busy.value)return;deleting.value=catalog.value.find(a=>a.id===id)||null;}
async function confirmDelete(){const a=deleting.value;if(!a||busy.value)return;busy.value=true;
 try{const r=await fetch('/api/collection/items/'+encodeURIComponent(a.id),{method:'DELETE',headers:{'X-SCAN3D-Client':'museum'}});const result=await r.json();if(!r.ok)throw Error(result.error||'删除失败');
  if(activeId.value===a.id&&screen.value==='exhibit'){
   cancelAI();stopVoice();const removedScene=scene;
   if(removedScene){clearTimeout(removedScene.saveTimer);removedScene.savePending=false;removedScene.dispose();await removedScene.saveTask?.catch(()=>{});}
   scene=undefined;loaded.value=false;screen.value='cabinet';history.replaceState(null,'',location.pathname+location.search);await nextTick();
  }
  let cleaned=true;try{await clearLocalExhibit(a);}catch{cleaned=false;}
  catalog.value=catalog.value.filter(x=>x.id!==a.id);delete records.value[a.id];deleting.value=null;
  if(activeId.value===a.id){activeId.value=catalog.value[0]?.id||'';fillDraft();}
  notice(cleaned?'展品已彻底删除':'展品已删除，本机缓存将在下次打开时继续清理');
 }catch(e:any){notice(e.message||'删除失败，请重试');}finally{busy.value=false;}
}
function yawInput(v:number){record.value.yaw=v;persist();}
onMounted(async()=>{void refreshAI();voiceAvailable.value='speechSynthesis'in window;try{const r=await fetch('/api/collection/catalog',{signal:abort.signal,cache:'no-store'});if(!r.ok)throw Error('展品目录加载失败');const listing=await r.json();catalog.value=listing.assets;for(const removed of listing.deleted)try{await clearLocalExhibit(removed);}catch{}catalogReady.value=true;if(destroyed)return;for(const a of catalog.value){try{records.value[a.id]=loadRecord(a);}catch{records.value[a.id]=defaults(a);notice('部分本机档案无法读取，已加载默认介绍');}}activeId.value=catalog.value[0]?.id||'';try{const last=localStorage.getItem('scan3d-museum-active');if(catalog.value.some(a=>a.id===last))activeId.value=last!;}catch{}fillDraft();readRoute();window.addEventListener('popstate',readRoute);window.addEventListener('hashchange',readRoute);}catch(e:any){if(e.name!=='AbortError')fatal.value=e.message;}});
onBeforeUnmount(()=>{cancelAI();destroyed=true;abort.abort();clearTimeout(toastTimer);stopVoice();window.removeEventListener('popstate',readRoute);window.removeEventListener('hashchange',readRoute);});
</script>

<template>
<div class="museum-app" :class="{'cabinet-mode':screen==='cabinet'}">
 <div v-if="fatal" class="museum-fatal">{{fatal}}<button @click="reload">重新打开</button></div>
 <CabinetGallery v-else-if="screen==='cabinet'&&catalogReady" :assets="displayCatalog" :records="records" :disabled="busy" @open="selectExhibit"/>
 <main v-else-if="current&&record" class="museum-layout">

  <section class="exhibition" :aria-label="record.name">
   <div class="exhibit-stage"><ExhibitViewport :key="activeId+'-'+viewKey" :asset="current" :yaw="record.yaw" @ready="ready" @notice="notice" @selected="pick" @sampled="sampleColor"/><div class="stage-controls"><button :class="{chosen:autoRotate}" :disabled="!loaded||panel==='paint'" @click="autoRotate=!autoRotate;syncScene()">{{autoRotate?'Ⅱ 停止旋转':'↻ 慢慢旋转'}}</button><button :disabled="!loaded" @click="scene?.perform('reset');autoRotate=false;syncScene()">↺ 重置视角</button><button :disabled="!loaded" @click="screenshot" aria-label="保存展品图片">▧</button><button @click="showInfo=!showInfo" aria-label="查看模型来源" :aria-pressed="showInfo">模型来源</button><button v-if="panel==='record'&&record.versions.length" @click="restoreStory">恢复上一版故事</button></div>
   <div v-if="showInfo" class="source-overlay"><button class="close" @click="showInfo=false" aria-label="关闭来源说明">×</button><h3>每个形状，都有来处。</h3><p>来源扫描 <code>{{current.source_scan}}</code></p><p>{{current.processing}}</p><p>{{current.segmentation_note}}</p><p>包围盒尺寸受展示朝向影响，不能作为测量精度承诺。</p><a v-if="current.source_stl" :href="current.source_stl" download class="button">下载原始 STL 副本 ↗</a></div></div>
   <div class="exhibit-summary"><div><span>网格高度</span><b>{{current.bounds_mm[1].toFixed(1)}} <small>mm</small></b></div><div><span>展示三角面</span><b>{{(current.faces/1000).toFixed(1)}} <small>k</small></b></div></div>
  </section>
  <aside class="curator-panel"><nav class="curator-tabs" aria-label="展品工具"><button v-for="t in [['story','听它讲述'],['paint','自由上色'],['record','展品档案']]" :key="t[0]" :class="{active:panel===t[0]}" @click="setPanel(t[0])">{{t[1]}}</button></nav>
   <section v-if="panel==='story'" class="story-panel"><div class="panel-heading"><div><h3>嗨，我是{{record.name}}。</h3></div><button class="round-button" :disabled="!voiceAvailable" @click="readCurrent" :aria-label="speaking?'停止朗读':'朗读当前讲述'">{{speaking?'■':'♪'}}</button></div><div ref="chatBody" class="chat-body"><article class="introduction"><span class="quote-mark">“</span><p>{{intro?.text}}</p></article><article v-for="(m,i) in record.messages" :key="i" class="chat-message" :class="m.role"><span>{{m.role==='user'?'你':record.name}}</span><p>{{displayMessage(m)}}</p><button v-if="m.role==='user'" class="remember-message" @click="rememberMessage(m.text)">记入故事</button><span v-if="m.role==='exhibit' && !m.source?.startsWith('档案互动')" class="reply-origin">{{m.source||'离线档案'}}</span></article></div><div class="suggestion-grid"><button v-for="q in suggestions" :key="q" :disabled="aiPending" @click="send(q)">{{q}} <span>↗</span></button></div><form class="ask-form" @submit.prevent="send()"><input v-model="query" maxlength="220" aria-label="给展品的问题"><button :disabled="!query.trim()||aiPending" aria-label="发送问题">↑</button></form><div class="story-footer"><button v-if="aiPending" @click="cancelAI">停止回答</button><button @click="clearChat" :disabled="!record.messages.length">清空对话</button></div><button class="greet-button" :disabled="!loaded" @click="greet">✧ 和{{record.name}}打个招呼</button></section>
   <section v-else-if="panel==='paint'" class="color-panel">
    <div class="paint-tool-switch" role="group" aria-label="上色工具">
     <button :class="{active:tool==='select'}" @click="setTool('select')" :disabled="!loaded">分区填色</button>
     <button :class="{active:tool==='brush'}" @click="setTool('brush')" :disabled="!loaded" title="左键涂色，右键旋转">自由画笔</button>
     <button :class="{active:tool==='erase'}" @click="setTool('erase')" :disabled="!loaded" title="擦除局部涂色，恢复分区颜色">橡皮擦</button>
     <button :class="{active:tool==='eyedropper'}" @click="setTool('eyedropper')" :disabled="!loaded" title="点击模型取色，随后自动切回画笔">取色笔</button>
    </div>
    <template v-if="tool==='select'">
     <div class="region-grid"><button v-for="(r,i) in current.regions" :key="i" :class="{selected:selected===i}" @click="pick(i)" :disabled="!loaded"><i :style="{background:palette[i]}"></i>{{r}}</button></div>
     <div class="museum-color-picker"><input type="color" :value="palette[selected]||'#ffffff'" @input="color(($event.target as HTMLInputElement).value)" :disabled="!loaded" aria-label="选中部位颜色"><div><b>{{current.regions[selected]}}</b><input v-model="hex" @input="color(hex)" maxlength="7" aria-label="颜色代码" spellcheck="false"></div></div>
     <div class="palette-presets"><button @click="preset('default')" :disabled="!loaded">默认</button><button @click="preset('ivory')" :disabled="!loaded">暖陶白</button><button @click="preset('porcelain')" :disabled="!loaded">青瓷</button><button @click="preset('clay')" :disabled="!loaded">赤陶</button></div>
    </template>
    <template v-else>
     <div v-if="tool==='brush'" class="brush-library" role="group" aria-label="笔触类型">
      <button v-for="b in BRUSHES" :key="b.id" :class="['brush-choice',b.id,{active:brushStyle===b.id}]" :aria-pressed="brushStyle===b.id" :aria-label="b.name+'笔触'" :title="b.tip" :disabled="!loaded" @click="chooseBrush(b.id)">
       <svg viewBox="0 0 76 28" aria-hidden="true"><path d="M6 21C14 3 18 5 23 17S36 25 41 12S54 8 58 16S68 20 70 9"/></svg><span>{{b.name}}</span>
      </button>
     </div>
     <div v-if="tool==='brush'||tool==='eyedropper'" class="museum-color-picker"><input type="color" v-model="brushColor" @input="syncScene" aria-label="画笔颜色"><div><b>画笔颜色</b><input :value="brushColor" @input="brushHex(($event.target as HTMLInputElement).value)" maxlength="7" aria-label="画笔颜色代码" spellcheck="false"></div></div>
     <div v-if="tool==='brush'" class="brush-swatches"><button v-for="c in ['#e895b3','#efbb54','#4b86ac','#789770','#eee8d8','#343a3a']" :key="c" :style="{background:c}" :aria-label="'画笔颜色 '+c" :class="{chosen:brushColor===c}" @click="brushHex(c)"></button></div>
     <label v-if="tool!=='eyedropper'" class="range-label">画笔半径 {{radius.toFixed(1)}} mm<input type="range" min=".3" max="8" step=".1" v-model.number="radius" @input="syncScene" aria-label="画笔半径"></label>
     <label v-if="tool==='brush'" class="range-label brush-opacity">浓度 {{Math.round(brushOpacity*100)}}%<input type="range" min=".1" max="1" step=".05" v-model.number="brushOpacity" @input="syncScene" aria-label="笔触浓度"></label>
    </template>
    <div class="surface-tools"><div class="checks"><label><input type="checkbox" v-model="softEdges" @change="setSoftEdges" :disabled="!loaded">颜色边缘平滑</label><label v-if="tool==='select'"><input type="checkbox" v-model="highlight" @change="syncScene">高亮分区</label><label><input type="checkbox" v-model="neutral" @change="syncScene">素色 STL</label></div><div class="tool-actions"><button @click="undo" :disabled="!undoCount">撤销上一笔</button><button @click="clearPaint" :disabled="!loaded">清除涂色</button></div></div>
    <button class="button full dark" @click="exportModel" :disabled="!loaded||busy">导出彩色 GLB ↗</button>
   </section>
   <section v-else class="record-panel"><div class="record-fields"><label>展品名字<input v-model="draft.name" maxlength="32" aria-label="展品名字"></label><label>物品类别<input v-model="draft.category" maxlength="64" aria-label="物品类别"></label><label>外形特点 <textarea v-model="draft.features" rows="2" maxlength="800" aria-label="外形特点"></textarea></label><label>相遇日期 / 纪念生日<input v-model="draft.acquiredDate" type="date" aria-label="相遇日期"></label><label>相遇地点<input v-model="draft.acquiredPlace" maxlength="100" placeholder="例如：青岛旅行时购买" aria-label="相遇地点"></label><label>它和你的故事 <small>{{(draft.story||'').length}} / 4000</small><textarea v-model="draft.story" rows="5" maxlength="4000" placeholder="记下相遇、旅行、赠送或制作的故事，也可以在聊天后点击「记入故事」。" aria-label="个人经历"></textarea></label><label class="tone-row">讲述语气<select v-model="draft.tone" aria-label="讲述语气"><option value="warm">温暖、亲切</option><option value="concise">简洁、客观</option></select></label><label class="range-label">展示朝向 {{record.yaw}}°<input type="range" min="-180" max="180" step="5" :value="record.yaw" @input="yawInput(Number(($event.target as HTMLInputElement).value))" aria-label="展品朝向"></label></div><button class="button full dark" @click="saveDraft()">{{dirty?'保存档案并更新讲述':'档案已保存 · 更新讲述'}}</button></section>
   <div class="exhibit-actions" role="group" aria-label="展品操作"><button class="button quiet exhibit-delete" @click="requestDelete(activeId)" :disabled="busy" aria-label="删除当前展品">删除</button><button class="button quiet" @click="goCabinet" :disabled="busy">← 返回陈列柜</button><label class="button quiet" :class="{disabled:busy}">导入展品包<input type="file" accept=".zip" aria-label="导入展品包" @change="importPackage" :disabled="busy"></label><button class="button dark" :disabled="!loaded||busy" @click="exportPackage">{{busy?'正在处理…':'保存展品包 ↗'}}</button></div>
  </aside>
 </main>
 <div v-else class="museum-fatal" role="status" aria-label="正在打开陈列馆"><span class="cabinet-loading" aria-hidden="true"></span></div>

 <div v-if="toast" class="museum-toast" role="status">{{toast}}</div>
 <div v-if="deleting" class="dialog-backdrop" @keydown.esc="!busy&&(deleting=null)"><div class="import-dialog" role="alertdialog" aria-modal="true" aria-labelledby="delete-exhibit-title"><h3 id="delete-exhibit-title">彻底删除「{{records[deleting.id]?.name||deleting.name}}」？</h3><p>删除陈列馆中的模型、本机档案、对话、配色和预览缓存。原始扫描和 STL 保留。</p><p>删除后无法撤销，需要时可从扫描结果重新导入。</p><div><button class="button" autofocus @click="deleting=null" :disabled="busy">取消</button><button class="button danger-delete" @click="confirmDelete" :disabled="busy">{{busy?'正在删除…':'彻底删除'}}</button></div></div></div>
 <div v-if="pending" class="dialog-backdrop"><div class="import-dialog" role="dialog" aria-modal="true" aria-label="导入展品包"><h3>恢复「{{pending.record.name}}」？</h3><p>包内模型与「{{pending.asset.name}}」几何一致。继续将替换这件展品在当前浏览器的档案、对话和配色，其他展品不受影响。</p><p>如需保留现在的内容，请先取消并导出当前展品包。</p><div><button class="button" @click="pending=null" :disabled="busy">取消</button><button class="button dark" @click="applyImport" :disabled="busy">恢复此展品</button></div></div></div>
</div>
</template>
