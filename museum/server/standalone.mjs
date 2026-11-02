import http from 'node:http';
import {createReadStream} from 'node:fs';
import {stat} from 'node:fs/promises';
import {resolve,extname,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createAIMiddleware} from './museum-ai.mjs';
import {collectionAPI,collectionRoot} from './collection.mjs';

const root=fileURLToPath(new URL('../dist/',import.meta.url));
const port=Number(process.env.MUSEUM_PORT||8830);
const hosts=(process.env.MUSEUM_HOSTS||'127.0.0.1:8830,localhost:8830,192.168.1.89:8830').split(',');
const api=createAIMiddleware({allowedHosts:hosts});
const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.woff2':'font/woff2','.glb':'model/gltf-binary','.stl':'model/stl','.ply':'application/octet-stream','.bin':'application/octet-stream'};
const server=http.createServer(async(req,res)=>{
 res.setHeader('X-Content-Type-Options','nosniff');
 res.setHeader('Referrer-Policy','same-origin');
 res.setHeader('Content-Security-Policy',"frame-ancestors 'self' http://192.168.1.89:8081 http://127.0.0.1:8081 http://localhost:8081 http://127.0.0.1:8834");
 if(!hosts.includes(req.headers.host||'')){res.writeHead(403);res.end();return;}
 if(await collectionAPI(req,res))return;
 await api(req,res,async()=>{
  if(!['GET','HEAD'].includes(req.method)){res.writeHead(405);res.end();return;}
  let path;try{path=decodeURIComponent(new URL(req.url,'http://localhost').pathname);}catch{res.writeHead(400);res.end();return;}
  if(path==='/')path='/index.html';
  const parts=path.split('/');
  if(parts.some(p=>p.startsWith('.')||p.includes('\\'))||!(path==='/index.html'||path.startsWith('/assets/')||path.startsWith('/museum/')||path.startsWith('/licenses/'))){res.writeHead(404);res.end();return;}
  const imported=path.startsWith('/museum/imports/');
  if(imported&&!/^\/museum\/imports\/scan-[a-f0-9]{24}\/(vertices.bin|faces.bin|face-regions.bin|face-adjacency.bin|asset.json|thumbnail.svg)$/.test(path)){res.writeHead(404);res.end();return;}
  const base=imported?resolve(collectionRoot):resolve(root);
  const file=imported?resolve(base,path.slice('/museum/imports/'.length)):resolve(base,'.'+path);
  if(!file.startsWith(base+sep)){res.writeHead(404);res.end();return;}
  try{
   const info=await stat(file);if(!info.isFile())throw Error();
   res.writeHead(200,{'Content-Type':types[extname(file)]||'application/octet-stream','Content-Length':info.size,'Cache-Control':imported&&path.endsWith('.bin')?'private, max-age=31536000, immutable':path.startsWith('/assets/')?'public, max-age=86400':'no-cache'});
   if(req.method==='HEAD'){res.end();return;}
   const stream=createReadStream(file);stream.on('error',()=>res.destroy());stream.pipe(res);
  }catch{res.writeHead(404);res.end();}
 });
});
server.requestTimeout=60000;
server.headersTimeout=15000;
server.listen(port,process.env.MUSEUM_BIND||'0.0.0.0',()=>console.log(`Museum listening on ${port}`));
process.on('SIGTERM',()=>{server.close();setTimeout(()=>process.exit(0),3000).unref();});
