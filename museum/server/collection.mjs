import {mkdir,readdir,readFile,writeFile,rename,rm,lstat,realpath} from 'node:fs/promises';
import {createHash,randomUUID} from 'node:crypto';
import {join,resolve,sep} from 'node:path';
import {fileURLToPath} from 'node:url';

export const collectionRoot=process.env.MUSEUM_COLLECTION_DIR||new URL('../assets/collection/',import.meta.url).pathname.replace(/^\/(\w:)/,'$1');
export const museumRoot=process.env.MUSEUM_CATALOG_DIR||fileURLToPath(new URL('../public/museum/',import.meta.url));
export async function deletedCollection(root=collectionRoot){try{return JSON.parse(await readFile(join(root,'deleted.json'),'utf8'));}catch(e){if(e.code==='ENOENT')return [];throw e;}}
async function restoreDeleted(id,root){const deleted=await deletedCollection(root);if(!deleted.some(a=>a.id===id))return;const tmp=join(root,'.deleted-'+randomUUID());await writeFile(tmp,JSON.stringify(deleted.filter(a=>a.id!==id)));await rename(tmp,join(root,'deleted.json'));}
export async function collectionCatalog(root=collectionRoot,museum=museumRoot){const deleted=await deletedCollection(root),ids=new Set(deleted.map(a=>a.id)),builtins=JSON.parse(await readFile(join(museum,'catalog.json'),'utf8'));return {assets:[...builtins,...await listCollection(root)].filter(a=>!ids.has(a.id)),deleted};}
async function safeRemove(root,relative){
 const base=await realpath(root),target=resolve(base,relative);
 if(!target.startsWith(base+sep)||target===base)throw Error('删除路径无效');
 // Refuse traversal through any symlink component; never follow a model outside its store.
 let current=base;for(const part of relative.split('/')){current=join(current,part);try{if((await lstat(current)).isSymbolicLink())throw Error('展品目录不能是符号链接');}catch(e){if(e.code==='ENOENT')return;throw e;}}
 await rm(target,{recursive:true,force:true});
}
export async function deleteCollection(id,root=collectionRoot,museum=museumRoot){
 if(!/^[a-z][a-z0-9-]{0,63}$/.test(id))throw Error('展品编号无效');
 const builtins=JSON.parse(await readFile(join(museum,'catalog.json'),'utf8'));
 const asset=[...builtins,...await listCollection(root)].find(a=>a.id===id);
 const deleted=await deletedCollection(root),prior=deleted.find(a=>a.id===id);
 if(!asset&&!prior)throw Error('展品不存在');
 const entry=prior||{id,geometry_key:asset.geometry_key};
 if(!/^scan-[a-f0-9]{24}$/.test(id)&&asset?.asset_base!=='/museum/'+id+'/')throw Error('展品目录不匹配');
 if(!prior){await mkdir(root,{recursive:true});const tmp=join(root,'.deleted-'+randomUUID());await writeFile(tmp,JSON.stringify([...deleted,entry]));await rename(tmp,join(root,'deleted.json'));}
 if(/^scan-[a-f0-9]{24}$/.test(id))await safeRemove(root,id);
 else {if(asset?.asset_base!=='/museum/'+id+'/')throw Error('展品目录不匹配');await safeRemove(museum,id);await safeRemove(museum,'rgb-v1/'+id);}
 return {deleted:true,...entry};
}
export async function listCollection(root=collectionRoot){
 let names;try{names=await readdir(root);}catch(e){if(e.code==='ENOENT')return [];throw e;}
 const assets=[];for(const name of names.filter(n=>/^scan-[a-f0-9]{24}$/.test(n))){assets.push(JSON.parse(await readFile(join(root,name,'asset.json'),'utf8')));}return assets;
}
export async function saveCollection(body,root=collectionRoot){
 if(body.length<4||body.length>24*1024*1024)throw Error('导入数据大小无效');
 const size=body.readUInt32LE(0);if(size>16000||size+4>body.length)throw Error('展品信息无效');
 const m=JSON.parse(body.subarray(4,4+size).toString('utf8'));
 const f=m.faces,v=m.vertices;if(!Number.isInteger(f)||f<1||f>200000||!Number.isInteger(v)||v<3||v>f*3)throw Error('模型面数或顶点数无效');
 const lengths=[v*12,f*12,f,f*12];if(lengths.reduce((a,b)=>a+b,4+size)!==body.length)throw Error('模型数据长度不匹配');
 if(!['cloud','plain'].includes(m.mode)||!Array.isArray(m.bounds_mm)||m.bounds_mm.length!==3||!m.bounds_mm.every(x=>Number.isFinite(x)&&x>=0&&x<=10000)||m.bounds_mm[1]<.001)throw Error('模型尺寸无效');
 if(!Array.isArray(m.palette)||m.palette.length!==8||!m.palette.every(c=>/^#[a-f0-9]{6}$/i.test(c)))throw Error('展品颜色无效');
 const buffers=[];let offset=4+size;for(const len of lengths){buffers.push(body.subarray(offset,offset+len));offset+=len;}
 for(let i=0;i<v*3;i++)if(!Number.isFinite(buffers[0].readFloatLE(i*4)))throw Error('模型坐标无效');
 for(let i=0;i<f*3;i++)if(buffers[1].readUInt32LE(i*4)>=v)throw Error('三角面索引无效');
 for(const x of buffers[2])if(x>7)throw Error('分区数据无效');
 for(let i=0;i<f*3;i++){const x=buffers[3].readInt32LE(i*4);if(x< -1||x>=f)throw Error('邻接数据无效');}
 const hash=createHash('sha256').update(body).digest('hex'),id='scan-'+hash.slice(0,24),base='/museum/imports/'+id+'/';
 const text=(x,n)=>typeof x==='string'?x.trim().slice(0,n):'';
 const regions=Array.from({length:8},(_,i)=>text(m.regions?.[i],24)||`色区 ${i+1}`);
 const note=m.mode==='cloud'?'按扫描点云颜色聚类分区':'素色展示，可自由上色';
 const asset={id,name:text(m.name,32)||'新展品',category:'扫描物品',subtitle:'从扫描结果加入陈列馆',regions,palette:m.palette,faces:f,vertices:v,bounds_mm:m.bounds_mm,geometry_key:hash,source_scan:text(m.source_scan,120),source_task:text(m.source_task,120),source_stl_sha256:'',source_stl:'',features:[],processing:'导入所选 STL，保留三角面；居中并对齐展示底面。',segmentation_note:note,transform:m.transform,asset_base:base,thumbnail:base+'thumbnail.svg',color_segmentation:{version:'scan-import-v1',regions,palette:m.palette,labels_file:'face-regions.bin',note,report_url:base+'asset.json',region_count:new Set(buffers[2]).size,measured_area_fraction:Math.max(0,Math.min(1,Number(m.measured_area_fraction)||0)),unknown_faces:buffers[2].reduce((n,x)=>n+(x===7?1:0),0)}};
 await mkdir(root,{recursive:true});try{const existing=JSON.parse(await readFile(join(root,id,'asset.json'),'utf8'));await restoreDeleted(id,root);return existing;}catch(e){if(e.code!=='ENOENT')throw e;}
 const staging=join(root,'.pending-'+randomUUID());await mkdir(staging);
 try{
  for(const [i,name] of ['vertices.bin','faces.bin','face-regions.bin','face-adjacency.bin'].entries())await writeFile(join(staging,name),buffers[i]);
  await writeFile(join(staging,'asset.json'),JSON.stringify(asset));
  await writeFile(join(staging,'thumbnail.svg'),'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160"><path d="m80 24 48 28v56l-48 28-48-28V52Zm0 56v56M32 52l48 28 48-28M80 24v56" fill="#e7dfd0" stroke="#68796b" stroke-width="3"/></svg>');
  await rename(staging,join(root,id));
  await restoreDeleted(id,root);
 }catch(e){await rm(staging,{recursive:true,force:true});throw e;}
 return asset;
}
let importing=false;
export async function collectionAPI(req,res){
 const path=req.url?.split('?')[0],deletion=path?.match(/^\/api\/collection\/items\/([a-z][a-z0-9-]{0,63})$/);if(!['/api/collection','/api/collection/import','/api/collection/catalog'].includes(path)&&!deletion)return false;
 const reply=(s,d)=>{res.writeHead(s,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify(d));};
 if(path==='/api/collection'&&req.method==='GET'){try{reply(200,await listCollection());}catch{reply(500,{error:'陈列馆目录读取失败'});}return true;}
 if(path==='/api/collection/catalog'&&req.method==='GET'){try{reply(200,await collectionCatalog());}catch{reply(500,{error:'陈列馆目录读取失败'});}return true;}
 if(deletion){
  if(req.method!=='DELETE'){reply(405,{error:'请求方式无效'});return true;}
  if(req.headers.origin!=='http://'+req.headers.host||req.headers['x-scan3d-client']!=='museum'){reply(403,{error:'请从陈列柜操作'});return true;}
  if(importing){reply(409,{error:'展品正在更新，请稍后再试'});return true;}
  importing=true;try{reply(200,await deleteCollection(deletion[1]));}catch(e){reply(400,{error:e.code?'展品删除失败，请重试':e.message});}finally{importing=false;}return true;
 }
 if(path!=='/api/collection/import'||req.method!=='POST'){reply(405,{error:'请求方式无效'});return true;}
 if(req.headers.origin!=='http://'+req.headers.host||req.headers['x-scan3d-client']!=='museum'){reply(403,{error:'请从扫描结果页面导入'});return true;}
 if(importing){reply(409,{error:'另一个展品正在导入，请稍后再试'});return true;}
 importing=true;
 try{const chunks=[];let size=0;for await(const chunk of req){size+=chunk.length;if(size>24*1024*1024)throw Error('导入文件超过 24 MB');chunks.push(chunk);}reply(200,await saveCollection(Buffer.concat(chunks)));}
 catch(e){reply(400,{error:e.code==='ENOSPC'?'板端空间不足，未导入展品':e instanceof SyntaxError?'展品信息格式无效':e.code?'展品保存失败':e.message});}finally{importing=false;}
 return true;
}
