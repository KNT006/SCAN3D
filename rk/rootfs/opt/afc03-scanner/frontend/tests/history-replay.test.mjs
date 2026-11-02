import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const source=readFileSync(new URL('../src/Scan3D.vue',import.meta.url),'utf8');
const slice=(a,b)=>source.slice(source.indexOf(a),source.indexOf(b,source.indexOf(a)));
const deployed=process.env.SCAN3D_DEPLOYED_SNIPPETS?JSON.parse(readFileSync(process.env.SCAN3D_DEPLOYED_SNIPPETS,'utf8')):null;
const functions=slice('const historyLocked=','const policy=')+(deployed?deployed.select+deployed.replay+'\nconst selectRun=nt,replay=ft;':slice('async function selectRun(){','let historyPolling=')+slice('function finishReplay(','watch([index,laser]'));
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject}};
const flush=async()=>{for(let i=0;i<5;i++)await new Promise(setImmediate)};
const ref=value=>({value});
function harness(){
 const requests=[],notices=[],timers=[];
 const ctx={selected:ref('old'),active:ref('new-scan'),state:ref({}),busy:ref(false),tab:ref(3),index:ref(0),laser:ref('A'),details:ref(null),audit:ref(null),replaying:ref(false),profileRow:ref(1000),stage:ref(0),replayPositions:ref([0,53]),disposed:false,replayEpoch:0,detailsToken:0,flowReplayPending:false,replayTimer:null,
  computed:fn=>({get value(){return fn()}}),resetCloud(){},applyCloudSummary(){},cloudLoads:0,loadCloud(){ctx.cloudLoads++},nextTick:()=>Promise.resolve(),notify:(...args)=>notices.push(args),setTimeout:(fn,ms)=>{timers.push({fn,ms});return timers.length},AbortSignal:{timeout:ms=>({timeout:ms})},
  api(path,body,signal){const d=deferred();requests.push({path,body,signal,...d});return d.promise},Error};
 if(deployed){for(const [original,alias] of Object.entries(deployed.aliases)){if(original in ctx)Object.defineProperty(ctx,alias,{get:()=>ctx[original],set:v=>{ctx[original]=v},configurable:true})}}
 vm.createContext(ctx);vm.runInContext(ts.transpileModule(functions,{compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText,ctx);if(deployed)ctx.Ce=vm.runInContext('historyLocked',ctx);
 return {ctx,requests,notices,timers,run:code=>vm.runInContext(code,ctx),async tick(){const t=timers.shift();assert.ok(t,'expected scheduled retry');t.fn();await flush();return t.ms}};
}
const result={status:'complete',roi:[140,1000,880,1660],steps:[{uv:[[500,1100]]}],final_count:1};
async function resolveSuccess(h,request=h.requests.at(-1),id='r2'){request.resolve({id});await flush();h.requests.at(-1).resolve(result);await flush()}
test('historical analysis remains available during another active scan; current scan explains restriction',()=>{
 const h=harness();assert.equal(h.run('historyLocked.value'),false);assert.equal(h.run('historyReplayHint.value'),'');
 h.ctx.selected.value='new-scan';assert.equal(h.run('historyLocked.value'),true);assert.match(h.run('historyReplayHint.value'),/选择其他已保存扫描/);h.run('replay()');assert.equal(h.requests.length,0);
 h.ctx.selected.value='old';h.ctx.state.value.mesh_processing=true;assert.equal(h.run('historyLocked.value'),true);
});
test('flow and parameters request lightweight details; results starts cloud independently',async()=>{
 for(const tab of [0,2,3]){const h=harness();h.ctx.tab.value=tab;const done=h.run('selectRun()');assert.equal(h.requests[0].path,'/runs/old/details?include_cloud=false');
 h.requests[0].resolve({id:'old',image_positions:[0,53]});await done;await flush();assert.equal(h.ctx.details.value.id,'old');assert.equal(h.ctx.cloudLoads,tab===2?1:0);
 if(tab===3){assert.equal(h.requests[1].body.run,'old');await resolveSuccess(h,h.requests[1]);assert.equal(h.ctx.audit.value._id,'r2')}}
});
test('late details cannot overwrite new selected archive',async()=>{
 const h=harness();h.ctx.tab.value=0;const a=h.run('selectRun()');h.ctx.selected.value='other';const b=h.run('selectRun()');h.requests[1].resolve({id:'other'});await b;h.requests[0].resolve({id:'old'});await a;assert.equal(h.ctx.details.value.id,'other');
});
test('POST timeout clears computing state without automatic resubmission',async()=>{
 const h=harness();const a=h.run('replay()');assert.equal(h.requests[0].signal.timeout,15000);const e=new Error('timeout');e.name='TimeoutError';h.requests[0].reject(e);await a;
 assert.equal(h.ctx.replaying.value,false);assert.equal(h.requests.length,1);assert.match(h.notices[0][0],/提交回放请求超时/);
});
test('queued archive survives old POST failure without stale error or mixed result',async()=>{
 const h=harness();const a=h.run('replay()');h.ctx.selected.value='other';const b=h.run('selectRun()');h.requests[1].resolve({id:'other'});await b;assert.equal(h.ctx.flowReplayPending,true);
 h.requests[0].reject(Error('old failed'));await a;await flush();assert.equal(h.requests[2].body.run,'other');assert.equal(h.ctx.flowReplayPending,false);await resolveSuccess(h,h.requests[2]);assert.equal(h.ctx.audit.value._id,'r2');assert.equal(h.notices.some(n=>n[0].includes('old failed')),false);
});
test('temporary polling disconnect retries same worker, does not resubmit',async()=>{
 const h=harness();const a=h.run('replay()');h.requests[0].resolve({id:'same'});await a;await flush();h.requests[1].reject(Error('offline'));await flush();assert.equal(h.ctx.replaying.value,true);assert.equal(await h.tick(),1500);
 assert.equal(h.requests[2].path,'/replay/same');h.requests[2].resolve(result);await flush();assert.equal(h.ctx.replaying.value,false);assert.equal(h.ctx.audit.value._id,'same');assert.equal(h.requests.filter(r=>r.body).length,1);
});
test('poll retries bounded at three and queued selection drains after exhaustion',async()=>{
 const h=harness();const a=h.run('replay()');h.requests[0].resolve({id:'old'});await a;await flush();h.ctx.selected.value='other';h.ctx.flowReplayPending=true;
 for(let i=0;i<4;i++){h.requests.at(-1).reject(Error('offline'));await flush();if(i<3)await h.tick()}
 assert.equal(h.timers.length,0);assert.equal(h.requests.at(-1).path,'/replay');assert.equal(h.requests.at(-1).body.run,'other');await resolveSuccess(h);assert.equal(h.ctx.replaying.value,false);
});
test('unmounted view discards late poll response and pending selection',async()=>{
 const h=harness();const a=h.run('replay()');h.requests[0].resolve({id:'old'});await a;await flush();h.ctx.disposed=true;h.ctx.flowReplayPending=true;h.requests[1].resolve(result);await flush();assert.equal(h.ctx.audit.value,null);assert.equal(h.requests.length,2);assert.equal(h.timers.length,0);
});
test('api applies supplied abort to replay POST without limiting hardware POST',async()=>{
 const requests=[],abort=new AbortController();let pending;
 const ctx={fetch(url,options){requests.push({url,options});return new Promise((resolve,reject)=>{pending={resolve,reject};options.signal?.addEventListener('abort',()=>reject(options.signal.reason),{once:true})})},AbortSignal};
 vm.createContext(ctx);vm.runInContext(ts.transpileModule(deployed?deployed.api+'\nconst api=Ae;':slice('async function api(','let toastTimer'),{compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText,ctx);
 ctx.signal=abort.signal;const a=vm.runInContext("api('/replay',{run:'old'},signal)",ctx);assert.equal(requests[0].options.signal,abort.signal);abort.abort(new DOMException('timeout','TimeoutError'));await assert.rejects(a,{name:'TimeoutError'});
 const b=vm.runInContext("api('/control',{op:'move'})",ctx);assert.equal(requests[1].options.signal,undefined);pending.resolve({ok:true,json:async()=>({done:true})});await b;
});
