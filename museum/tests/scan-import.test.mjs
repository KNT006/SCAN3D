import assert from 'node:assert/strict';
import {mkdtemp,rm,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {prepareScan} from '../src/museum/ScanImport.worker.ts';
import {saveCollection,listCollection} from '../server/collection.mjs';
const binary=new ArrayBuffer(184),d=new DataView(binary);d.setUint32(80,2,true);
const tris=[[0,0,0, 1,0,0, 0,1,0],[1,0,0, 1,1,0, 0,1,0]];
tris.forEach((tri,i)=>tri.forEach((x,k)=>d.setFloat32(84+i*50+12+k*4,x,true)));
const input={stl:binary,name:'测试展品',run:'scan-test',task:'mesh-test',mode:'plain'};
const plain=prepareScan(input);assert.equal(plain.meta.vertices,4);assert.equal(plain.meta.faces,2);
assert.deepEqual(Array.from(new Uint8Array(plain.buffers[2])),[0,0]);
assert.equal(Array.from(new Int32Array(plain.buffers[3])).filter(x=>x>=0).length,2);
const colored=prepareScan({...input,mode:'cloud',xyz:new Float32Array([.33,.33,0,.67,.67,0]).buffer,rgb:new Uint8Array([240,0,0,0,0,240]).buffer});
assert.equal(colored.meta.matched,2);assert.equal(new Set(new Uint8Array(colored.buffers[2])).size,2);
assert.equal(colored.meta.measured_area_fraction,1);
assert.throws(()=>prepareScan({...input,mode:'cloud',xyz:new Float32Array([100,100,100]).buffer,rgb:new Uint8Array([0,0,0]).buffer}),/对齐/);
function pack(result){const meta=Buffer.from(JSON.stringify(result.meta)),h=Buffer.alloc(4);h.writeUInt32LE(meta.length);return Buffer.concat([h,meta,...result.buffers.map(b=>Buffer.from(b))]);}
const dir=await mkdtemp(join(tmpdir(),'scan3d-import-'));
try{
 const body=pack(colored),a=await saveCollection(body,dir),b=await saveCollection(body,dir);
 assert.equal(a.id,b.id);assert.equal((await listCollection(dir)).length,1);
 assert.equal(a.name,'测试展品');assert.deepEqual(await readFile(join(dir,a.id,'face-regions.bin')),Buffer.from(colored.buffers[2]));
 await assert.rejects(saveCollection(body.subarray(0,body.length-1),dir),/长度/);
 const bad=prepareScan(input);new Uint32Array(bad.buffers[1])[0]=500;await assert.rejects(saveCollection(pack(bad),dir),/索引/);
 assert.equal((await listCollection(dir)).length,1);
}finally{await rm(dir,{recursive:true,force:true});}
console.log('PASS: preserved geometry, adjacency, two-colour regions, missing coverage, persistence, duplicate import and invalid payloads');
