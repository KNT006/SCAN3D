import {zipSync,unzipSync,strToU8,strFromU8} from 'three/addons/libs/fflate.module.js';
import {GLTFExporter} from 'three/addons/exporters/GLTFExporter.js';
import * as T from 'three';
import type {ExhibitAsset,ExhibitRecord} from './MuseumData';
import {validateRecord} from './MuseumData.ts';
import type {DuckPaint} from '../DuckPaint';
import {resolveSegmentation,paintKey} from './MuseumSegmentation.ts';
export function downloadBlob(blob:Blob,name:string){const u=URL.createObjectURL(blob),a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),10000);}
export async function makeGLB(asset:ExhibitAsset,paint:DuckPaint){const highlight=paint.highlight,neutral=paint.neutral;paint.highlight=false;paint.neutral=false;paint.refresh();const g=paint.round?paint.round.exportGeometry():paint.exportGeometry(),m=paint.round?new T.PointsMaterial({vertexColors:true,size:.0004}):new T.MeshStandardMaterial({vertexColors:true,roughness:.7}),mesh=paint.round?new T.Points(g,m):new T.Mesh(g,m);paint.highlight=highlight;paint.neutral=neutral;paint.refresh();mesh.name=asset.id+'_scanned_exhibit';mesh.userData={source_scan:asset.source_scan,geometry_key:asset.geometry_key,color:'user assigned, not measured',units:'meters'};try{return await new GLTFExporter().parseAsync(mesh,{binary:true}) as ArrayBuffer;}finally{g.dispose();m.dispose();}}
export async function makeArchive(a:ExhibitAsset,r:ExhibitRecord,paint:DuckPaint,buffers:ArrayBuffer[]){
 const glb=await makeGLB(a,paint);const manifest={format:'scan3d-exhibit',version:paint.round?3:2,asset:a,record:validateRecord(a,r),palette:paint.palette,softEdges:paint.softEdges};
 return zipSync({'exhibit.json':strToU8(JSON.stringify(manifest,null,2)),'model.glb':new Uint8Array(glb),'face-regions.bin':paint.labels.slice(),'face-paint.bin':new Uint8Array(paint.faceColors.buffer.slice(0)),'surface-paint.bin':new Uint8Array(paint.surface.data.buffer.slice(0)),...(paint.round?{'round-paint.bin':new Uint8Array(paint.round.data.buffer.slice(0))}:{}),'vertices.bin':new Uint8Array(buffers[0]),'faces.bin':new Uint8Array(buffers[1]),'face-adjacency.bin':new Uint8Array(buffers[3]),'README.txt':strToU8('SCAN3D 物品陈列馆\nmodel.glb：可独立打开的彩色展示模型，单位为米。\nexhibit.json：展品档案、来源与自选配色。\n其余 bin 文件：可编辑分区与毫米几何。\n在陈列馆中导入此 ZIP 可恢复匹配展品的档案和上色。\n颜色为用户创作；推断/封底区域不代表新增实测数据。\n原始 STL/点云不被本展品包替换。')},{level:1});
}
export async function readArchive(file:File,catalog:ExhibitAsset[]){
 if(file.size>32*1024*1024)throw Error('展品包超过 32 MB');
 let total=0;const files=unzipSync(new Uint8Array(await file.arrayBuffer()),{filter:(f:any)=>{total+=f.originalSize;if(total>64*1024*1024)throw Error('展品包解压后过大');return ['exhibit.json','face-regions.bin','face-paint.bin','surface-paint.bin','round-paint.bin'].includes(f.name);}});
 if(!files['exhibit.json']||files['exhibit.json'].length>150000||!files['face-regions.bin'])throw Error('缺少有效档案或分区文件');
 const d=JSON.parse(strFromU8(files['exhibit.json']));const base=catalog.find(a=>a.id===d.asset?.id&&a.geometry_key===d.asset?.geometry_key);
 if(d.format!=='scan3d-exhibit'||![1,2,3].includes(d.version)||!base)throw Error('展品包与当前陈列馆模型不匹配');
 const a=resolveSegmentation(base);
 if(d.asset?.segmentation_mode!=='rgb')throw Error('只支持当前照片辅助分区展品包');
 if(d.asset?.paint_key&&d.asset.paint_key!==paintKey(a))throw Error('展品包的分区版本与当前版本不同，未覆盖任何数据');
 const labels=files['face-regions.bin'];if(labels.length!==a.faces||!labels.every((n:number)=>n<8)||!Array.isArray(d.palette)||d.palette.length!==8||!d.palette.every((s:any)=>typeof s==='string'&&/^#[0-9a-f]{6}$/i.test(s)))throw Error('分区或颜色数据无效');
 const raw=files['face-paint.bin'];if(raw&&raw.byteLength!==a.faces*4)throw Error('涂色数据长度无效');
 const faceColors=raw?new Int32Array(raw.slice().buffer):new Int32Array(a.faces).fill(-1);if(!faceColors.every(n=>n>=-1&&n<=0xffffff))throw Error('涂色数据无效');
 const surfaceRaw=files['surface-paint.bin'];if(d.version>=2&&!surfaceRaw)throw Error('缺少平滑涂色层');if(surfaceRaw&&surfaceRaw.byteLength!==a.faces*3*4*4)throw Error('平滑涂色数据长度无效');
 const surface=surfaceRaw?new Float32Array(surfaceRaw.slice().buffer):new Float32Array(a.faces*12);if(!surface.every(n=>Number.isFinite(n)&&n>=0&&n<=1))throw Error('平滑涂色数据无效');
 const roundRaw=files['round-paint.bin'];if(d.version===3&&!roundRaw)throw Error('缺少圆点涂色层');if(roundRaw&&(roundRaw.byteLength%16||roundRaw.byteLength>400000*16))throw Error('圆点涂色数据长度无效');const round=roundRaw?new Float32Array(roundRaw.slice().buffer):undefined;if(round&&!round.every(x=>Number.isFinite(x)&&x>=0&&x<=1))throw Error('圆点涂色数据无效');
 return {asset:a,record:validateRecord(a,d.record),paint:{labels:labels.slice(),palette:[...d.palette],faceColors,surface,round,softEdges:typeof d.softEdges==='boolean'?d.softEdges:true}};
}
