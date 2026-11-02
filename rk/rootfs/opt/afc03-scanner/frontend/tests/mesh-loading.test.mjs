import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const source=readFileSync(new URL('../src/MeshTasks.vue',import.meta.url),'utf8');
const code=source.slice(source.indexOf('let generation='),source.indexOf('watch(selected,'));
const flush=async()=>{for(let i=0;i<6;i++)await new Promise(setImmediate)};
function harness(){
 const calls=[],timers=new Map();let timerId=0,change;
 const ctx={props:{run:'old'},AbortController,Set,Error,JSON,errorZh:e=>String(e),setTimeout(fn,ms){timers.set(++timerId,{fn,ms});return timerId},clearTimeout(id){timers.delete(id)},watch(get,fn){change=fn;fn()},fetch(url,options){return new Promise((resolve,reject)=>{calls.push({url,options,resolve:data=>resolve({ok:true,json:async()=>data}),reject});options.signal.addEventListener('abort',()=>reject(Error('aborted')),{once:true})})}};
 for(const key of ['sources','tasks','selected','source','legacyMesh','legacy','error','scanState','sourceLoading','busy'])ctx[key]={value:null};
 vm.createContext(ctx);vm.runInContext(ts.transpileModule(code,{compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText,ctx);
 return {ctx,calls,timers,change,run:code=>vm.runInContext(code,ctx)};
}
const completed=[{id:'saved-stl',status:'complete'}];
test('existing STL available while source inventory and metadata remain unresolved',async()=>{
 const h=harness();assert.equal(h.calls.length,4);assert.ok(h.calls[0].url.endsWith('/mesh-tasks'));
 h.calls[0].resolve(completed);await flush();assert.equal(h.ctx.selected.value,'saved-stl');assert.equal(h.ctx.sourceLoading.value,true);
 assert.ok(h.calls.some(c=>c.url.endsWith('/details?include_cloud=false')));
});
test('failed sources cannot prevent existing mesh selection or polling',async()=>{
 const h=harness();h.calls.find(c=>c.url.endsWith('/mesh-sources')).reject(Error('slow source timeout'));
 h.calls[0].resolve(completed);await flush();assert.equal(h.ctx.selected.value,'saved-stl');assert.equal(h.ctx.sourceLoading.value,false);
 assert.equal([...h.timers.values()].filter(t=>t.ms===1500).length,1);
});
test('archive switch aborts old requests and ignores stale model responses',async()=>{
 const h=harness();h.calls[0].resolve(completed);h.ctx.props.run='new';h.change();await flush();
 assert.ok(h.calls.slice(0,4).every(c=>c.options.signal.aborted));assert.equal(h.ctx.selected.value,'');
 h.calls[4].resolve([{id:'new-stl',status:'complete'}]);await flush();assert.equal(h.ctx.selected.value,'new-stl');
 assert.equal([...h.timers.values()].filter(t=>t.ms===1500).length,1);
});
test('poll is serial and late unmounted responses cannot update selection',async()=>{
 const h=harness();assert.equal([...h.timers.values()].filter(t=>t.ms===1500).length,0);
 h.run('disposed=true;generation++;clearTimeout(timer);abortRequests()');await flush();assert.equal(h.ctx.selected.value,'');assert.equal(h.timers.size,0);
});
