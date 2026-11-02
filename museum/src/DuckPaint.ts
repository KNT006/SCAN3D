import {RoundSurface} from './RoundSurface.ts';
import {SurfaceBrush} from './SurfaceBrush.ts';
import type {BrushOptions} from './BrushProfiles.ts';
import * as T from 'three';
import {RegionEdgeSmoothing} from './RegionEdgeSmoothing.ts';
export const REGION_NAMES=['身体','头部','嘴部','左眼','左翼','右翼','尾部','右眼'];
export const DEFAULT_PALETTE=['#f4e5bd','#f4e5bd','#e88b35','#26312d','#f4e5bd','#f4e5bd','#f4e5bd','#26312d'];
export class DuckPaint {
 round?:RoundSurface;
 enableRoundSurface(){this.round=new RoundSurface(this.geometry);this.round.seedLegacy(this.surface.data);this.refresh();}
 restoreRoundAsSurface(layer:unknown){
  if(this.round||!(layer instanceof Float32Array)||!layer.every(x=>Number.isFinite(x)&&x>=0&&x<=1))return;
  const samples=new RoundSurface(this.geometry);
  try{if(layer.length===samples.data.length)this.surface.replace(samples.toSurface(layer));}
  finally{samples.geometry.dispose();}
 }

 edgeSmoothing?:RegionEdgeSmoothing;softEdges=true;surface:SurfaceBrush;
 enableEdgeSmoothing(material:T.MeshStandardMaterial){this.edgeSmoothing=new RegionEdgeSmoothing(this.geometry,this.adj);this.edgeSmoothing.install(material);this.refresh();}
 geometry:T.BufferGeometry;labels:Uint8Array;original:Uint8Array;adj:Int32Array;centers:Float32Array;palette:string[];faceColors:Int32Array;history:{labels:Uint8Array;faceColors:Int32Array;surface:Float32Array;round?:Float32Array}[]=[];stroke:{labels:Uint8Array;faceColors:Int32Array;surface:Float32Array;round?:Float32Array}|null=null;changed=false;selected=0;highlight=false;neutral=false;
 constructor(indexed:T.BufferGeometry,labels:Uint8Array,adj:Int32Array){const sourceIndex=Array.from(indexed.index!.array);this.geometry=indexed.toNonIndexed();this.surface=new SurfaceBrush(this.geometry,sourceIndex);indexed.dispose();this.labels=labels.slice();this.faceColors=new Int32Array(labels.length).fill(-1);this.original=labels.slice();this.adj=adj;this.palette=[...DEFAULT_PALETTE];const p=this.geometry.getAttribute('position');this.centers=new Float32Array(labels.length*3);for(let i=0;i<labels.length;i++)for(let k=0;k<3;k++)this.centers[i*3+k]=(p.array[i*9+k]+p.array[i*9+3+k]+p.array[i*9+6+k])/3;this.geometry.setAttribute('color',new T.BufferAttribute(new Float32Array(p.count*3),3));this.refresh();}
 refresh(){const attr=this.geometry.getAttribute('color'),arr=attr.array as Float32Array;const colors=this.palette.map(c=>new T.Color(c));for(let f=0;f<this.labels.length;f++){const c=this.neutral?new T.Color('#e4e3d9'):this.faceColors[f]>=0?new T.Color(this.faceColors[f]):colors[this.labels[f]];let r=c.r,g=c.g,b=c.b;if(this.highlight&&this.labels[f]===this.selected){r=r*.6+.12;g=g*.6+.32;b=b*.6+.12;}for(let j=0;j<3;j++){const i=f*9+j*3;arr[i]=r;arr[i+1]=g;arr[i+2]=b;}}attr.needsUpdate=true;if(this.edgeSmoothing){this.edgeSmoothing.enabled.value=this.softEdges&&!this.highlight&&!this.neutral?1:0;this.edgeSmoothing.paintEnabled.value=this.neutral?0:1;this.edgeSmoothing.update(this.labels,this.faceColors);}this.round?.refresh(this.softEdges&&!this.highlight,this.neutral);}
 /** Read paint/region sRGB, excluding scene lights, highlights and tone mapping. */
 colorAt(face:number,point?:T.Vector3):string|null{
  if(!Number.isInteger(face)||face<0||face>=this.labels.length)return null;
  if(point&&this.round)return this.round.sample(face,point);
  if(point){const b=this.barycentric(face,point),layer=this.surface.sample(face,b);let rgb:number[];
   if(this.edgeSmoothing){const neutral=this.edgeSmoothing.paintEnabled.value;this.edgeSmoothing.paintEnabled.value=0;const hi=this.highlight,ne=this.neutral;this.highlight=false;this.neutral=false;this.refresh();this.edgeSmoothing.paintEnabled.value=0;rgb=this.edgeSmoothing.sampleColor(face,b);this.highlight=hi;this.neutral=ne;this.refresh();this.edgeSmoothing.paintEnabled.value=neutral;}
   else{const base=new T.Color(this.faceColors[face]>=0?this.faceColors[face]:this.palette[this.labels[face]]);rgb=[base.r,base.g,base.b];}
   return '#'+new T.Color().setRGB(rgb[0]*(1-layer[3])+layer[0],rgb[1]*(1-layer[3])+layer[1],rgb[2]*(1-layer[3])+layer[2]).getHexString();
  }
  const c=this.faceColors[face];return c>=0?'#'+c.toString(16).padStart(6,'0'):this.palette[this.labels[face]].toLowerCase();
 }
 begin(){if(!this.stroke){this.stroke={labels:this.labels.slice(),faceColors:this.faceColors.slice(),surface:this.surface.data.slice(),round:this.round?.data.slice()};this.surface.beginStroke();this.round?.begin();this.changed=false;}}
 brush(face:number,radius:number,region:number){if(face<0||face>=this.labels.length)return 0;const q=[face],seen=new Set<number>(q),ox=this.centers[face*3],oy=this.centers[face*3+1],oz=this.centers[face*3+2];let count=0;while(q.length){const i=q.pop()!,dx=this.centers[i*3]-ox,dy=this.centers[i*3+1]-oy,dz=this.centers[i*3+2]-oz;if(dx*dx+dy*dy+dz*dz>radius*radius)continue;if(this.labels[i]!==region){this.labels[i]=region;count++;}for(let j=0;j<3;j++){const n=this.adj[i*3+j];if(n>=0&&!seen.has(n)){seen.add(n);q.push(n);}}}if(count){this.changed=true;this.refresh();}return count;}
 /** Apply an independent sRGB brush layer without changing photo region labels. */
 paintColor(face:number,radius:number,color:string|null){
  if(!Number.isInteger(face)||face<0||face>=this.labels.length||!Number.isFinite(radius)||radius<=0)return 0;
  if(color!==null&&!/^#[0-9a-f]{6}$/i.test(color))return 0;
  const value=color===null?-1:parseInt(color.slice(1),16),q=[face],seen=new Set<number>(q);
  const ox=this.centers[face*3],oy=this.centers[face*3+1],oz=this.centers[face*3+2];let count=0;
  while(q.length){const f=q.pop()!,dx=this.centers[f*3]-ox,dy=this.centers[f*3+1]-oy,dz=this.centers[f*3+2]-oz;
   if(dx*dx+dy*dy+dz*dz>radius*radius)continue;
   if(this.faceColors[f]!==value){this.faceColors[f]=value;count++;}
   for(let j=0;j<3;j++){const n=this.adj[f*3+j];if(n>=0&&!seen.has(n)){seen.add(n);q.push(n);}}
  }
  if(count){this.changed=true;this.refresh();}return count;
 }
 barycentric(face:number,point:T.Vector3){const p=this.geometry.getAttribute('position');return new T.Triangle(new T.Vector3().fromBufferAttribute(p,face*3),new T.Vector3().fromBufferAttribute(p,face*3+1),new T.Vector3().fromBufferAttribute(p,face*3+2)).getBarycoord(point,new T.Vector3())?.toArray()||[1/3,1/3,1/3];}
 smoothPaint(face:number,radius:number,color:string|null,point:T.Vector3,options:BrushOptions={}){
  if(!Number.isInteger(face)||face<0||face>=this.labels.length||!Number.isFinite(radius)||radius<=0||!point.toArray().every(Number.isFinite)||(color!==null&&!/^#[0-9a-f]{6}$/i.test(color)))return 0;
  // Move legacy per-face paint into the editable layer without losing saved colors.
  let promoted=false;for(let f=0;f<this.faceColors.length;f++)if(this.faceColors[f]>=0){const c=new T.Color(this.faceColors[f]);for(let j=0;j<3;j++){const o=(f*3+j)*4;this.surface.data.set([c.r,c.g,c.b,1],o);}this.faceColors[f]=-1;promoted=true;}
  const n=this.round?this.round.stamp(face,point,radius,color,this.adj,options):this.surface.stamp(face,point,radius,color,this.adj,options);if(n||promoted){this.changed=true;this.surface.dirty();if(promoted)this.refresh();}return n;
 }
 clearPaint(){this.begin();this.changed=this.faceColors.some(c=>c>=0)||this.surface.data.some(c=>c>0)||!!this.round?.data.some(c=>c>0);this.faceColors.fill(-1);this.surface.data.fill(0);this.round?.data.fill(0);this.surface.dirty();this.commit();this.refresh();}
 commit(){if(this.stroke&&this.changed){this.history.push(this.stroke);while(this.history.length>20||this.history.length>1&&this.history.length*(this.surface.data.byteLength+this.faceColors.byteLength+this.labels.byteLength+(this.round?.data.byteLength||0))>32*1024*1024)this.history.shift();}this.stroke=null;this.surface.endStroke();this.round?.end();this.changed=false;}
 undo(){const a=this.history.pop();if(a){this.labels=a.labels;this.faceColors=a.faceColors;this.surface.replace(a.surface);if(this.round&&a.round)this.round.data.set(a.round);this.refresh();return true;}return false;}
 resetRegions(){this.begin();this.labels=this.original.slice();this.changed=true;this.commit();this.refresh();}
 restore(data:any){if(data?.labels instanceof Uint8Array&&data.labels.length===this.labels.length&&data.labels.every((v:number)=>v<8))this.labels=data.labels.slice();if(Array.isArray(data?.palette)&&data.palette.length===8&&data.palette.every((c:any)=>typeof c==='string'&&/^#[0-9a-f]{6}$/i.test(c)))this.palette=[...data.palette];if(data?.faceColors instanceof Int32Array&&data.faceColors.length===this.labels.length&&data.faceColors.every((v:number)=>v>=-1&&v<=0xffffff))this.faceColors=data.faceColors.slice();if(data?.surface instanceof Float32Array&&data.surface.length===this.surface.data.length&&data.surface.every((v:number)=>Number.isFinite(v)&&v>=0&&v<=1))this.surface.replace(data.surface);else if(data?.faceColors instanceof Int32Array)this.surface.replace(new Float32Array(this.surface.data.length));if(this.round){this.round.data.fill(0);if(data?.round instanceof Float32Array&&data.round.length===this.round.data.length&&data.round.every((x:number)=>Number.isFinite(x)&&x>=0&&x<=1))this.round.data.set(data.round);else this.round.seedLegacy(this.surface.data);}this.restoreRoundAsSurface(data?.round);if(typeof data?.softEdges==='boolean')this.softEdges=data.softEdges;this.refresh();}
 snapshot(){return{labels:this.labels.slice(),palette:[...this.palette],faceColors:this.faceColors.slice(),surface:this.surface.data.slice(),round:this.round?.data.slice(),softEdges:this.softEdges};}
 exportGeometry(){const h=this.highlight,n=this.neutral;this.highlight=false;this.neutral=false;this.refresh();let g:T.BufferGeometry;try{g=this.edgeSmoothing?this.edgeSmoothing.bake():this.geometry.clone();for(const key of Object.keys(g.attributes))if(key.startsWith('region')||key==='surfacePaint')g.deleteAttribute(key);g.scale(.001,.001,.001);}finally{this.highlight=h;this.neutral=n;this.refresh();}return g!;}
}
function db(){return new Promise<IDBDatabase>((resolve,reject)=>{const r=indexedDB.open('scan3d-duck-paint',1);r.onupgradeneeded=()=>r.result.createObjectStore('models');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});}
export async function loadPaint(key:string){const d=await db();return new Promise<any>((resolve,reject)=>{const tx=d.transaction('models','readonly'),r=tx.objectStore('models').get(key);r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);tx.oncomplete=()=>d.close();});}
export async function storePaint(key:string,data:any){const d=await db();return new Promise<void>((resolve,reject)=>{const tx=d.transaction('models','readwrite');tx.objectStore('models').put(data,key);tx.oncomplete=()=>{d.close();try{localStorage.setItem('scan3d-paint-revision:'+key,String(Date.now())+Math.random());window.dispatchEvent(new CustomEvent('scan3d-paint-saved',{detail:key}));}catch{}resolve();};tx.onerror=()=>{d.close();reject(tx.error);};});}

export async function deletePaintFamily(geometryKey:string){const d=await db();return new Promise<void>((resolve,reject)=>{const tx=d.transaction('models','readwrite'),store=tx.objectStore('models'),request=store.openKeyCursor();request.onsuccess=()=>{const c=request.result;if(!c)return;const key=String(c.key);if(key===geometryKey||key.startsWith(geometryKey+':'))store.delete(c.key);c.continue();};tx.oncomplete=()=>{d.close();resolve();};tx.onerror=()=>{d.close();reject(tx.error);};});}
