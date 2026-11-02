import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const source=readFileSync(new URL('../src/Scan3D.vue',import.meta.url),'utf8');
const funcs=source.slice(source.indexOf('let cloudSummary:'),source.indexOf('let historyPolling='));
const ref=value=>({value});
function harness(){
 const pending=[],ctx={selected:ref('old'),resultMode:ref('points'),tab:ref(2),active:ref(null),cloudLoading:ref(false),cloudError:ref(''),resultCloud:ref(null),details:ref(null),index:ref(0),audit:ref(null),disposed:false,cloudToken:0,detailsToken:0,cloudRequest:null,AbortController,parseResultCloud:()=>({count:2}),summarizeResultCloud:()=>({count:2,bounds_mm:[1,2,3]}),errorZh:e=>e.message,notify(){},fetch:()=>new Promise(resolve=>pending.push(resolve)),api:()=>new Promise(()=>{})};
 vm.createContext(ctx);vm.runInContext(ts.transpileModule(funcs,{compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText,ctx);return {ctx,pending,run:s=>vm.runInContext(s,ctx)};
}
test('cloud begins without waiting for details; metadata can arrive later',async()=>{const h=harness();h.run('selectRun()');assert.equal(h.pending.length,1);h.pending[0]({ok:true,arrayBuffer:async()=>new ArrayBuffer(0)});await new Promise(setImmediate);assert.equal(h.ctx.resultCloud.value.count,2);h.ctx.details.value={id:'old'};h.run('applyCloudSummary()');assert.equal(h.ctx.details.value.count,2)});
test('STL view never fetches cloud; duplicate requests are suppressed',()=>{const h=harness();h.ctx.resultMode.value='stl';h.run('loadCloud()');assert.equal(h.pending.length,0);h.ctx.resultMode.value='points';h.run('loadCloud();loadCloud()');assert.equal(h.pending.length,1)});
test('late old cloud is discarded after archive switch',async()=>{const h=harness();const done=h.run('loadCloud()');h.ctx.selected.value='new';h.run('resetCloud()');h.pending[0]({ok:true,arrayBuffer:async()=>new ArrayBuffer(0)});await done;assert.equal(h.ctx.resultCloud.value,null)});
const binaryModule={exports:{}};
vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/cloudBinary.ts',import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText,{exports:binaryModule.exports});
test('summary preserves all downloaded points and exact axis extents',()=>{const xyz=new Float32Array([-2,5,0,3,1,7]),copy=xyz.slice();const s=binaryModule.exports.summarizeResultCloud({xyz,count:2,total:2});assert.equal(s.count,2);assert.deepEqual(Array.from(s.bounds_mm),[5,4,7]);assert.deepEqual(xyz,copy);assert.equal(binaryModule.exports.summarizeResultCloud({xyz:new Float32Array(),count:0,total:0}).bounds_mm,null)});
