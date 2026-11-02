import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,stat,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve,sep} from 'node:path';
import http from 'node:http';
const base=await mkdtemp(join(tmpdir(),'museum-delete-test-')),root=join(base,'collection'),museum=join(base,'museum');
assert(resolve(base).startsWith(resolve(tmpdir())+sep));
await mkdir(root);await mkdir(museum);
process.env.MUSEUM_COLLECTION_DIR=root;process.env.MUSEUM_CATALOG_DIR=museum;
const {saveCollection,listCollection,deleteCollection,collectionCatalog,collectionAPI}=await import('../server/collection.mjs');
const meta={faces:1,vertices:3,mode:'plain',bounds_mm:[1,1,1],palette:Array(8).fill('#aabbcc'),name:'删除测试'};
const m=Buffer.from(JSON.stringify(meta)),head=Buffer.alloc(4);head.writeUInt32LE(m.length);
const vertices=Buffer.alloc(36),faces=Buffer.alloc(12),adj=Buffer.alloc(12,255);faces.writeUInt32LE(1,4);faces.writeUInt32LE(2,8);
const payload=Buffer.concat([head,m,vertices,faces,Buffer.alloc(1),adj]);
await writeFile(join(museum,'catalog.json'),JSON.stringify([{id:'fixture',geometry_key:'fixture-key',asset_base:'/museum/fixture/'}]));
await mkdir(join(museum,'fixture'));await writeFile(join(museum,'fixture','mesh.bin'),'fixture');
const server=http.createServer(async(req,res)=>{if(!await collectionAPI(req,res)){res.writeHead(404);res.end();}});
await new Promise(ok=>server.listen(0,'127.0.0.1',ok));const origin='http://127.0.0.1:'+server.address().port;
try{
 const a=await saveCollection(payload,root);
 const b=await saveCollection(Buffer.concat([head,m,Buffer.from(vertices.map((x,i)=>i===3?63:x)),faces,Buffer.alloc(1),adj]),root);
 assert.notEqual(a.id,b.id);
 const r=await fetch(origin+'/api/collection/items/'+a.id,{method:'DELETE'});assert.equal(r.status,403);assert.equal((await listCollection(root)).length,2);
 await assert.rejects(deleteCollection('../fixture',root,museum),/编号/);
 const good=await fetch(origin+'/api/collection/items/'+a.id,{method:'DELETE',headers:{Origin:origin,'X-SCAN3D-Client':'museum'}});assert.equal(good.status,200);
 await assert.rejects(stat(join(root,a.id)),{code:'ENOENT'});assert.equal((await listCollection(root)).length,1);assert.equal((await listCollection(root))[0].id,b.id);
 assert((await collectionCatalog(root,museum)).deleted.some(x=>x.id===a.id));
 await deleteCollection(a.id,root,museum); // Retry is idempotent.
 await saveCollection(payload,root);assert((await collectionCatalog(root,museum)).assets.some(x=>x.id===a.id));
 assert(!(await collectionCatalog(root,museum)).deleted.some(x=>x.id===a.id));
 await deleteCollection('fixture',root,museum);await assert.rejects(stat(join(museum,'fixture')),{code:'ENOENT'});
 assert(!(await collectionCatalog(root,museum)).assets.some(x=>x.id==='fixture'));
 assert((await readFile(join(root,b.id,'asset.json'))).length>0);
 console.log('PASS: same-origin deletion, physical removal, catalog persistence, other exhibits preserved, invalid IDs, retry and reimport.');
}finally{await new Promise(ok=>server.close(ok));await rm(base,{recursive:true,force:true});}
