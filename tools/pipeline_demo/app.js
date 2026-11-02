'use strict';
// Presentation-only client. The server retains diagnostics and background controls.
const canvas=document.getElementById('view'),ctx=canvas.getContext('2d');
const imageKeys=['original','difference','smoothed','original',null];
let stage=0,revision=-1,serverInstance=null,epoch=0,lifecycle=0,disposed=false;
let frameTimer=null,keyTimer=null,frameController=null,liveResult=null,bitmap=null,frameNo=0,lastError=null;
let lastDrawMs=null,lastFrameIdentity=null;
function releaseImage(){if(bitmap){bitmap.close();bitmap=null;}}
function clear(){ctx.fillStyle='#000';ctx.fillRect(0,0,canvas.width,canvas.height);}
async function api(path,body,signal){
 const r=await fetch(path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined,signal:signal||AbortSignal.timeout(12000),cache:'no-store'});
 const d=await r.json();if(!r.ok){const e=Error(d.error||d.detail||'Request failed');e.status=r.status;throw e;}return d;
}
async function picture(path,signal){const r=await fetch(path,{cache:'no-store',signal:signal||AbortSignal.timeout(9000)});if(!r.ok)throw Error('Image unavailable');return createImageBitmap(await r.blob());}
function restartFrames(){
 frameController?.abort();clearTimeout(frameTimer);
 if(!disposed)frameTimer=setTimeout(()=>loop(),0);
}
function setStage(s){
 if(!Number.isInteger(s)||s<0||s>=5||s===stage)return;
 stage=s;epoch++;
 canvas.dataset.requestedStage=String(s);canvas.dataset.switchRequestedMs=String(Date.now());
 delete canvas.dataset.switchLatencyMs;
 restartFrames(); // Do not wait for the previous stage's network request.
}
function applyState(s){
 if(s.instance!==serverInstance){
  const previous=serverInstance;serverInstance=s.instance;revision=-1;lastFrameIdentity=null;
  if(previous!==null){epoch++;restartFrames();}
 }
 if(s.revision>=revision){revision=s.revision;setStage(s.stage);}
}
function render(result,image,requestedStage){
 const [w,h]=result.preview_size||[540,960], [cw,ch]=result.coordinate_size||[1080,1920];
 if(canvas.width!==w)canvas.width=w;if(canvas.height!==h)canvas.height=h;
 clear();
 if(requestedStage!==4&&image)ctx.drawImage(image,0,0,w,h);
 if(requestedStage>=3){
  if(requestedStage===3){
   ctx.fillStyle='#000';
   for(const [x,y] of result.final_uv||[])ctx.fillRect(Math.round(x*w/cw)-2,Math.round(y*h/ch)-1,4,4);
  }
  ctx.fillStyle=requestedStage===4?'#fff':'#ff00ff';
  for(const [x,y] of result.final_uv||[])ctx.fillRect(Math.round(x*w/cw)-1,Math.round(y*h/ch),2,2);
 }
}
function recordDraw(requestedStage,started,sequence,timings){
 const now=Date.now();frameNo++;lastError=null;
 Object.assign(canvas.dataset,{frameCount:String(frameNo),lastUpdatedMs:String(now),intervalMs:lastDrawMs===null?'':String(now-lastDrawMs),renderMs:String(performance.now()-started),stage:String(requestedStage)});
 if(sequence!==undefined)canvas.dataset.sourceSequence=String(sequence);else delete canvas.dataset.sourceSequence;
 if(timings)canvas.dataset.processingTimings=JSON.stringify(timings);else delete canvas.dataset.processingTimings;
 if(canvas.dataset.requestedStage===String(requestedStage)&&canvas.dataset.switchRequestedMs!==undefined&&canvas.dataset.switchLatencyMs===undefined)
  canvas.dataset.switchLatencyMs=String(now-Number(canvas.dataset.switchRequestedMs));
 lastDrawMs=now;
}
function renderCamera(image){
 const started=performance.now();
 if(canvas.width!==540)canvas.width=540;if(canvas.height!==960)canvas.height=960;
 clear();ctx.save();ctx.translate(540,0);ctx.rotate(Math.PI/2);ctx.drawImage(image,0,0,960,540);ctx.restore();
 recordDraw(0,started);lastFrameIdentity=null;
}
function unavailableReason(message){
 // A busy computation or transient network error must not replace final stripes with raw video.
 return /扫描或其他处理|请仅开启|尚无原始背景|保存关激光背景|相机流已重启|重新保存背景|scanner busy|background required|laser OFF/i.test(message);
}
async function loop(g=lifecycle){
 if(disposed||g!==lifecycle)return;
 const controller=new AbortController();frameController=controller;
 const deadline=setTimeout(()=>controller.abort(),12000);
 let delay=30,nextImage=null;
 const e=epoch,requestedStage=stage;
 const valid=()=>!disposed&&g===lifecycle&&e===epoch&&requestedStage===stage&&!controller.signal.aborted&&frameController===controller;
 try{
  if(document.hidden){delay=250;}
  else if(requestedStage===0){
   nextImage=await picture('/camera.jpg',controller.signal);
   if(valid()){
    releaseImage();bitmap=nextImage;nextImage=null;liveResult=null;renderCamera(bitmap);
    delete canvas.dataset.fallbackReason;
   }
  }else{
   const result=await api('/api/live/frame?stage='+requestedStage,undefined,controller.signal);
   if(valid()){
    if(result.pending){
     delay=80;
     // Initial KEY state can be a processed stage: show the camera once while
     // its first result is computed, without replacing an existing stripe image.
     if(frameNo===0){
      nextImage=await picture('/camera.jpg',controller.signal);
      if(valid()){
       releaseImage();bitmap=nextImage;nextImage=null;liveResult=null;renderCamera(bitmap);
      }
     }
    }
    else if(result.stage!==undefined&&result.stage!==requestedStage){delay=80;}
    else{
     const identity=result.frame?.stream_id!==undefined&&result.frame?.sequence!==undefined
      ?JSON.stringify([serverInstance,result.background_generation,requestedStage,result.frame.stream_id,result.frame.sequence]):null;
     if(identity!==null&&identity===lastFrameIdentity){delay=80;}
     else{
      const key=imageKeys[requestedStage];
      if(key){const path=result.images?.[key]||(key==='smoothed'?result.images?.smooth:null);if(!path)throw Error('Missing stage image');nextImage=await picture(path,controller.signal);}
      if(valid()){
       releaseImage();bitmap=nextImage;nextImage=null;liveResult=result;
       const started=performance.now();render(result,bitmap,requestedStage);recordDraw(requestedStage,started,result.frame?.sequence,result.timings);
       lastFrameIdentity=identity;delete canvas.dataset.fallbackReason;
      }
     }
    }
   }
  }
 }catch(err){
  delay=250;
  if(valid()){
   lastError=String(err.message||err);
   if(requestedStage!==0&&(unavailableReason(lastError)||frameNo===0)){
    const reason=lastError;
    try{
     nextImage=await picture('/camera.jpg',controller.signal);
     if(valid()){
      releaseImage();bitmap=nextImage;nextImage=null;liveResult=null;
      renderCamera(bitmap);lastError=reason;canvas.dataset.fallbackReason=reason;
     }
    }catch{} // Both inputs unavailable: retain the last successfully drawn image.
   }
  }
 }finally{
  clearTimeout(deadline);if(nextImage)nextImage.close();
  if(frameController===controller){
   frameController=null;
   if(!disposed&&g===lifecycle&&e===epoch)frameTimer=setTimeout(()=>loop(g),delay);
  }
 }
}
async function keys(g=lifecycle){
 if(disposed||g!==lifecycle)return;
 try{const state=await api('/api/state');if(!disposed&&g===lifecycle)applyState(state);}catch{}
 if(!disposed&&g===lifecycle)keyTimer=setTimeout(()=>keys(g),100);
}
function next(){return api('/api/next',{}).then(s=>{if(!disposed)applyState(s);}).catch(()=>{});}
window.addEventListener('pagehide',()=>{disposed=true;epoch++;lifecycle++;frameController?.abort();clearTimeout(frameTimer);clearTimeout(keyTimer);releaseImage();liveResult=null;lastFrameIdentity=null;});
window.addEventListener('pageshow',e=>{if(e.persisted&&disposed){disposed=false;loop();keys();}});
document.addEventListener('keydown',e=>{if(!e.repeat&&['Space','ArrowRight','Enter'].includes(e.code)){e.preventDefault();next();}});
canvas.addEventListener('dblclick',()=>{const action=document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen();action?.catch(()=>{});});
clear();loop();keys();
