import assert from 'node:assert/strict';
import {PreviewBuffer} from '../src/previewBuffer.ts';
import {useScanMonitor} from '../src/useScanMonitor.ts';
const chunk=i=>({index:i,xyz:Array.from({length:50},(_,j)=>[i,j,0]),rgb:Array.from({length:50},(_,j)=>[i%256,j,0])});
const page=(id,i)=>({id,protocol:2,chunks:[chunk(i)],gaps:[],cursor:i,available_through:3199});
const oldDebug=console.debug;console.debug=()=>{};
const b=new PreviewBuffer(),t=performance.now();
for(let i=0;i<3200;i++){b.append(chunk(i));b.append(chunk(i))}
assert.equal(b.count,160000);assert.equal(b.seen.size,3200);assert.equal(b.xyz[(b.count-1)*3],3199);
const updateMs=performance.now()-t;
let stateResolve,pointResolve,mode='slow',calls=0;
const m=useScanMonitor(async(path,signal)=>{
 if(path.endsWith('/state'))return new Promise(r=>stateResolve=r);
 calls++;if(mode==='slow')return new Promise(r=>pointResolve=r);
 if(mode==='offline')throw Error('network unavailable');
 return page('new',0);
});
m.bind('old');const state=m.refreshState(),points=m.refreshPoints();await m.refreshPoints();assert.equal(calls,1);
pointResolve(page('old',0));await points;assert.equal(m.preview.value.count,50); // Slow state did not block points.
const stale=m.refreshPoints();m.bind('new');pointResolve(page('old',1));await stale;assert.equal(m.preview.value.count,0);
stateResolve({id:'old',status:'complete'});await state;assert.equal(m.state.value.id,'new');
mode='ok';await m.refreshPoints();assert.equal(m.preview.value.count,50);
mode='offline';await m.refreshPoints();assert.equal(m.preview.value.count,50);assert.match(m.error.value,/自动重连/);
mode='ok';await m.refreshPoints();assert.equal(m.preview.value.count,50);
m.setEnabled(false);assert.equal(m.preview.value.count,0);m.setEnabled(true);await new Promise(r=>setTimeout(r,0));assert.equal(m.preview.value.count,50);
m.dispose();const before=calls;await m.refreshPoints();assert.equal(calls,before);
// Missing positions remain retryable while later positions are displayed.
const realNow=Date.now;let now=realNow(),requests=[],gapCalls=0;
Date.now=()=>now;
const g=useScanMonitor(async path=>{
 requests.push(path);gapCalls++;
 if(gapCalls===1)return {...page('gaps',2),gaps:[{index:1,reason:'file_not_published'}]};
 if(path.includes('retry=1'))return {...page('gaps',1),cursor:2};
 return {...page('gaps',2),chunks:[],cursor:2};
});
try{
 g.bind('gaps');await g.refreshPoints();assert.match(g.progress.value,/补载 1 处/);
 await g.refreshPoints();assert.ok(!requests.at(-1).includes('retry=1'));
 now+=3000;await g.refreshPoints();assert.ok(requests.at(-1).includes('retry=1'));
 assert.equal(g.preview.value.count,100);assert.equal(g.preview.value.seen.size,2);
 assert.ok(!g.progress.value.includes('补载'));await g.refreshPoints();assert.equal(g.preview.value.count,100);
}finally{g.dispose();Date.now=realNow;}
console.debug=oldDebug;
console.log(JSON.stringify({passed:true,positions:b.seen.size,last:b.xyz[(b.count-1)*3],typedArrayBytes:b.xyz.byteLength+b.rgb.byteLength,appendMs:updateMs}));
