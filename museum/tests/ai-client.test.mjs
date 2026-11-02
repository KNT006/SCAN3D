import assert from 'node:assert/strict';import {askAI} from '../src/museum/MuseumAI.ts';
const native=globalThis.fetch;let sent;
const a={id:'duck',source_scan:'private-file-path'},r={name:'小鸭',category:'摆件',features:['无脚'],story:'',tone:'warm',messages:[]};
try{
 globalThis.fetch=async(url,o)=>{sent=JSON.parse(o.body);assert.equal(url,'/api/ai/chat');return new Response(JSON.stringify({text:'你好',action:'nod'}));};
 assert.equal((await askAI(a,r,'你好',new AbortController().signal)).action,'nod');assert(!JSON.stringify(sent).includes('private-file-path'));
 globalThis.fetch=async()=>new Response(JSON.stringify({text:'bad',action:'laser_on'}));await assert.rejects(askAI(a,r,'hi',new AbortController().signal),/格式无效/);
 globalThis.fetch=async()=>new Response(JSON.stringify({error:'连接不可用'}),{status:504});await assert.rejects(askAI(a,r,'hi',new AbortController().signal),/连接不可用/);
 globalThis.fetch=(u,o)=>new Promise((resolve,reject)=>o.signal.addEventListener('abort',()=>reject(new DOMException('cancelled','AbortError')),{once:true}));
 const c=new AbortController(),pending=askAI(a,r,'hi',c.signal);c.abort();await assert.rejects(pending,{name:'AbortError'});
}finally{globalThis.fetch=native;}
console.log('PASS: minimal text payload, action validation, explicit failure, cancellation.');
