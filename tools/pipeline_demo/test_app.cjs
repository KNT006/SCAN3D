'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'app.js'),'utf8');
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};}
const flush=async()=>{for(let i=0;i<4;i++)await new Promise(setImmediate);};
function harness(){
 const requests=[],timers=new Map(),events={},keyEvents={},bitmaps=[];let nextTimer=1;
 const ctx={rects:[],images:[],fillStyle:'',fillRect(...args){this.rects.push({color:this.fillStyle,args});},drawImage(...args){this.images.push(args);},save(){},translate(){},rotate(){},restore(){}};
 const canvas={dataset:{},width:540,height:960,getContext:()=>ctx,addEventListener(){}};
 const sandbox={console,Date,Math,Number,Promise,JSON,performance,AbortController,AbortSignal:{timeout:()=>new AbortController().signal},setTimeout(fn,ms){const id=nextTimer++;timers.set(id,{fn,ms});return id;},clearTimeout:id=>timers.delete(id),
 document:{hidden:false,getElementById:id=>{assert.equal(id,'view');return canvas;},addEventListener:(name,fn)=>keyEvents[name]=fn,documentElement:{requestFullscreen:async()=>{}},exitFullscreen:async()=>{}},window:{addEventListener:(name,fn)=>events[name]=fn},
 fetch(url,options){const d=deferred(),r={url,options,...d};requests.push(r);options.signal?.addEventListener('abort',()=>d.reject(Object.assign(Error('aborted'),{name:'AbortError'})),{once:true});return d.promise;},
 createImageBitmap:async blob=>{const im={width:540,height:960,closed:false,blob,close(){this.closed=true;}};bitmaps.push(im);return im;}};
 vm.createContext(sandbox);vm.runInContext(source,sandbox,{filename:'app.js'});
 return {sandbox,ctx,canvas,events,keyEvents,requests,timers,bitmaps,run:code=>vm.runInContext(code,sandbox),respond(req,value,ok=true,status=ok?200:503){req.resolve({ok,status,json:async()=>value,blob:async()=>value});},async tick(ms){const entry=[...timers.entries()].find(([,t])=>t.ms===ms);assert(entry,'missing timer '+ms);timers.delete(entry[0]);entry[1].fn();await flush();}};
}
function result(stage,seq=42,generation=1){const key=['original','difference','smooth','original',null][stage];return {stage,background_generation:generation,frame:{stream_id:'camera',sequence:seq},coordinate_size:[1080,1920],preview_size:[540,960],uv:[[540,960],[108,192]],final_uv:[[540,960]],images:key?{[key]:'data:'+key+','+seq}:{}};}
async function finish(h,value){const req=h.requests.at(-1);h.respond(req,value);await flush();for(const url of Object.values(value.images||{})){const image=h.requests.at(-1);assert.equal(image.url,url);h.respond(image,{});await flush();}}
async function switchTo(h,stage){h.run('setStage('+stage+')');await flush();await h.tick(0);}
async function final(h){await switchTo(h,4);await finish(h,result(4));}

test('only full-viewport canvas; no visible controls',()=>{
 const html=fs.readFileSync(path.join(__dirname,'index.html'),'utf8');assert.match(html,/object-fit:contain/);assert.match(html,/overflow:hidden/);assert.doesNotMatch(html,/<(?:button|header|aside|select|input|h1|p|span)\b/);assert.doesNotMatch(source,/二值|binary/);
});
test('raw video serial requests and closes replaced bitmap',async()=>{
 const h=harness();h.respond(h.requests[0],{});await flush();assert.equal(h.canvas.dataset.stage,'0');assert.equal(h.canvas.dataset.sourceSequence,undefined);
 await h.tick(30);const req=h.requests.at(-1);assert.equal(req.url,'/camera.jpg');assert.equal([...h.timers.values()].filter(t=>t.ms===30).length,0);
 h.respond(req,{});await flush();assert.equal(h.bitmaps[0].closed,true);assert.equal(h.run('frameNo'),2);
});
test('KEY stage change aborts delayed frame immediately without waiting for its response',async()=>{
 const h=harness(),old=h.requests[0];await switchTo(h,2);assert.equal(old.options.signal.aborted,true);assert.equal(h.requests.at(-1).url,'/api/live/frame?stage=2');
 await finish(h,result(2));assert.equal(h.canvas.dataset.stage,'2');assert.equal(h.run('frameNo'),1);assert.equal([...h.timers.values()].filter(t=>t.ms===30).length,1);
});
test('pending preserves processed image and never fetches raw fallback',async()=>{
 const h=harness();await final(h);const draws=h.ctx.rects.length;await h.tick(30);h.respond(h.requests.at(-1),{pending:true,stage:4},true,202);await flush();
 assert.equal(h.run('frameNo'),1);assert.equal(h.ctx.rects.length,draws);assert.equal(h.requests.at(-1).url,'/api/live/frame?stage=4');await h.tick(80);await finish(h,result(4,43));assert.equal(h.run('frameNo'),2);
});
test('cached source frame dedupes; new background generation or sequence draws',async()=>{
 const h=harness();await final(h);await h.tick(30);await finish(h,result(4));assert.equal(h.run('frameNo'),1);
 await h.tick(80);await finish(h,result(4,42,2));assert.equal(h.run('frameNo'),2);await h.tick(30);await finish(h,result(4,43,2));assert.equal(h.run('frameNo'),3);
});
test('final stripe overlay and black/white retain exact coordinate scaling',async()=>{
 const h=harness();await switchTo(h,3);await finish(h,result(3));assert.deepEqual(h.ctx.rects.slice(-2),[{color:'#000',args:[268,479,4,4]},{color:'#ff00ff',args:[269,480,2,2]}]);
 const drawCount=h.ctx.rects.length;await switchTo(h,4);assert.equal(h.ctx.rects.length,drawCount);await finish(h,result(4));assert.equal(h.bitmaps[0].closed,true);assert.deepEqual(h.ctx.rects.slice(-2),[{color:'#000',args:[0,0,540,960]},{color:'#fff',args:[269,480,2,2]}]);
});
test('transient network failure retains stripes, actual scanner busy falls back and recovers',async()=>{
 const h=harness();await final(h);await h.tick(30);h.requests.at(-1).reject(Error('network timeout'));await flush();assert.equal(h.canvas.dataset.stage,'4');assert.equal(h.run('frameNo'),1);assert.equal(h.requests.at(-1).url,'/api/live/frame?stage=4');
 await h.tick(250);h.respond(h.requests.at(-1),{error:'扫描或其他处理正在运行，实时条纹已让出资源'},false);await flush();assert.equal(h.requests.at(-1).url,'/camera.jpg');h.respond(h.requests.at(-1),{});await flush();assert.equal(h.canvas.dataset.stage,'0');assert.equal(h.run('stage'),4);
 await h.tick(250);await finish(h,result(4,44));assert.equal(h.canvas.dataset.stage,'4');assert.equal(h.canvas.dataset.fallbackReason,undefined);
});
test('rapid switch cancels previous request; wrong-stage response never draws',async()=>{
 const h=harness();await switchTo(h,1);const previous=h.requests.at(-1);await switchTo(h,4);assert.equal(previous.options.signal.aborted,true);h.respond(h.requests.at(-1),result(1));await flush();assert.equal(h.run('frameNo'),0);
 await h.tick(80);await finish(h,result(4));assert.equal(h.canvas.dataset.stage,'4');
});
test('pagehide aborts frame and BFCache restores one loop pair; stale key response ignored',async()=>{
 const h=harness(),oldKey=h.requests[1];await final(h);await h.tick(30);const old=h.requests.at(-1);h.events.pagehide();await flush();assert.equal(old.options.signal.aborted,true);assert.equal(h.timers.size,0);
 h.events.pageshow({persisted:true});const n=h.requests.length;h.events.pageshow({persisted:true});assert.equal(h.requests.length,n);h.respond(oldKey,{instance:'old',revision:99,stage:0});await flush();assert.equal(h.run('stage'),4);
 const fresh=h.requests.slice(-2);h.respond(fresh.find(r=>r.url==='/api/state'),{instance:'new',revision:0,stage:4});h.respond(fresh.find(r=>r.url.includes('/api/live/frame')),result(4,77));await flush();assert.deepEqual([...h.timers.values()].map(t=>t.ms).sort((a,b)=>a-b),[30,100]);
});

test('late bitmap decode after stage change is closed and cannot overwrite newer final frame',async()=>{
 const h=harness(),gate=deferred(),late={closed:false,close(){this.closed=true;}};
 await switchTo(h,1);h.respond(h.requests.at(-1),result(1));await flush();
 const imageReq=h.requests.at(-1);h.sandbox.createImageBitmap=async()=>{await gate.promise;return late;};h.respond(imageReq,{});await flush();
 await switchTo(h,4);await finish(h,result(4,88));assert.equal(h.canvas.dataset.stage,'4');
 gate.resolve();await flush();assert.equal(late.closed,true);assert.equal(h.canvas.dataset.stage,'4');assert.equal(h.canvas.dataset.sourceSequence,'88');assert.equal(h.run('frameNo'),1);
});

test('initial server stage pending shows camera once, then retains it until requested result',async()=>{
 const h=harness();h.respond(h.requests[1],{instance:'server',revision:7,stage:4});await flush();await h.tick(0);
 assert.equal(h.requests.at(-1).url,'/api/live/frame?stage=4');h.respond(h.requests.at(-1),{pending:true,stage:4},true,202);await flush();
 assert.equal(h.requests.at(-1).url,'/camera.jpg');h.respond(h.requests.at(-1),{});await flush();
 assert.equal(h.canvas.dataset.stage,'0');assert.equal(h.canvas.dataset.requestedStage,'4');assert.equal(h.canvas.dataset.switchLatencyMs,undefined);assert.equal(h.run('frameNo'),1);
 await h.tick(80);const requestCount=h.requests.length;h.respond(h.requests.at(-1),{pending:true,stage:4},true,202);await flush();assert.equal(h.requests.length,requestCount);assert.equal(h.run('frameNo'),1);
 await h.tick(80);await finish(h,result(4,99));assert.equal(h.canvas.dataset.stage,'4');assert(+h.canvas.dataset.switchLatencyMs>=0);
 const latency=h.canvas.dataset.switchLatencyMs,updated=h.canvas.dataset.lastUpdatedMs;await h.tick(30);await finish(h,result(4,99));assert.equal(h.canvas.dataset.switchLatencyMs,latency);assert.equal(h.canvas.dataset.lastUpdatedMs,updated);
});
