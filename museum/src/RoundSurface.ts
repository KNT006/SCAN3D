import * as T from 'three';
import {brushWeight} from './BrushProfiles.ts';
import type {BrushOptions} from './BrushProfiles.ts';

/** Deterministic area samples: round splats and a separate, surface-local circular paint layer. */
export class RoundSurface {
 geometry=new T.BufferGeometry();data:Float32Array;base:Float32Array;offsets:Uint32Array;bary:Float32Array;faceOf:Uint32Array;
 vertexIds:Uint32Array;vertexCount=0;spacing:number;neutral=false;
 stroke:Map<number,{base:Float32Array;coverage:number}>|null=null;
 source:T.BufferGeometry;
 constructor(source:T.BufferGeometry){
  this.source=source;
  const p=source.getAttribute('position'),normal=source.getAttribute('normal'),faces=p.count/3;
  const areas=new Float64Array(faces),a=new T.Vector3(),b=new T.Vector3(),c=new T.Vector3(),tri=new T.Triangle();let total=0;
  this.vertexIds=new Uint32Array(p.count);const keys=new Map<string,number>();
  for(let i=0;i<p.count;i++){const key=[p.getX(i),p.getY(i),p.getZ(i)].map(x=>Math.round(x*10000)).join(',');if(!keys.has(key))keys.set(key,keys.size);this.vertexIds[i]=keys.get(key)!;}this.vertexCount=keys.size;
  for(let f=0;f<faces;f++){tri.set(a.fromBufferAttribute(p,f*3),b.fromBufferAttribute(p,f*3+1),c.fromBufferAttribute(p,f*3+2));total+=areas[f]=tri.getArea();}
  const budget=Math.min(180000,Math.max(50000,Math.ceil(total/.035)));this.spacing=Math.sqrt(total/budget);
  this.offsets=new Uint32Array(faces+1);for(let f=0;f<faces;f++)this.offsets[f+1]=this.offsets[f]+Math.max(1,Math.floor(areas[f]/Math.max(total,1e-9)*budget));
  const count=this.offsets[faces],positions=new Float32Array(count*3),normals=new Float32Array(count*3);
  this.bary=new Float32Array(count*3);this.faceOf=new Uint32Array(count);this.data=new Float32Array(count*4);this.base=new Float32Array(count*3);
  for(let f=0;f<faces;f++)for(let i=this.offsets[f];i<this.offsets[f+1];i++){
   const j=i-this.offsets[f],n=this.offsets[f+1]-this.offsets[f],u=Math.sqrt((j+.5)/n),v=((j+.5)*.61803398875+f*.38196601125)%1,weights=[1-u,u*(1-v),u*v];
   this.bary.set(weights,i*3);this.faceOf[i]=f;
   for(let k=0;k<3;k++)for(let q=0;q<3;q++){positions[i*3+k]+=p.array[f*9+q*3+k]*weights[q];normals[i*3+k]+=normal.array[f*9+q*3+k]*weights[q];}
  }
  this.geometry.setAttribute('position',new T.BufferAttribute(positions,3));this.geometry.setAttribute('normal',new T.BufferAttribute(normals,3));this.geometry.setAttribute('color',new T.BufferAttribute(new Float32Array(count*3),3));
 }
 seedLegacy(layer:Float32Array){for(let i=0;i<this.faceOf.length;i++)for(let k=0;k<4;k++)for(let j=0;j<3;j++)this.data[i*4+k]+=layer[this.faceOf[i]*12+j*4+k]*this.bary[i*3+j];}
 /** Project saved splat paint back onto the original face corners for mesh painting. */
 toSurface(layer:Float32Array){
  if(layer.length!==this.data.length)throw Error('圆点涂色数据长度无效');
  const out=new Float32Array(this.source.getAttribute('position').count*4),weights=new Float64Array(out.length/4);
  for(let i=0;i<this.faceOf.length;i++)for(let j=0;j<3;j++){
   const v=this.faceOf[i]*3+j,w=this.bary[i*3+j];weights[v]+=w;
   for(let k=0;k<4;k++)out[v*4+k]+=layer[i*4+k]*w;
  }
  for(let v=0;v<weights.length;v++)if(weights[v])for(let k=0;k<4;k++)out[v*4+k]=Math.min(1,Math.max(0,out[v*4+k]/weights[v]));
  return out;
 }
 refresh(smooth:boolean,neutral:boolean){
  this.neutral=neutral;const colors=this.source.getAttribute('color').array,acc=new Float32Array(this.vertexCount*4);
  if(smooth)for(let i=0;i<this.vertexIds.length;i++){const j=this.vertexIds[i]*4;for(let k=0;k<3;k++)acc[j+k]+=colors[i*3+k];acc[j+3]++;}
  for(let i=0;i<this.faceOf.length;i++){const f=this.faceOf[i];for(let k=0;k<3;k++){
   let color=0;for(let j=0;j<3;j++){const id=this.vertexIds[f*3+j]*4;color+=this.bary[i*3+j]*(smooth?acc[id+k]/acc[id+3]:colors[f*9+j*3+k]);}this.base[i*3+k]=color;
  }this.compose(i);}this.geometry.getAttribute('color').needsUpdate=true;
 }
 compose(i:number){const out=this.geometry.getAttribute('color').array as Float32Array;for(let k=0;k<3;k++)out[i*3+k]=this.neutral?this.base[i*3+k]:this.base[i*3+k]*(1-this.data[i*4+3])+this.data[i*4+k];}
 begin(){this.stroke=new Map();}end(){this.stroke=null;}
 stamp(face:number,point:T.Vector3,radius:number,color:string|null,adj:Int32Array,options:BrushOptions={}){
  const p=this.source.getAttribute('position'),samples=this.geometry.getAttribute('position'),tri=new T.Triangle(),near=new T.Vector3();
  const queue=[face],seen=new Set(queue),rgb=color===null?null:new T.Color(color);let changed=0;
  while(queue.length){const f=queue.pop()!;tri.a.fromBufferAttribute(p,f*3);tri.b.fromBufferAttribute(p,f*3+1);tri.c.fromBufferAttribute(p,f*3+2);tri.closestPointToPoint(point,near);if(near.distanceToSquared(point)>radius*radius)continue;
   for(let i=this.offsets[f];i<this.offsets[f+1];i++){
    near.fromBufferAttribute(samples,i);const distance=near.distanceTo(point)/radius;if(distance>=1)continue;
    const weight=brushWeight(distance,near.x,near.y,near.z,color===null?{}:options);if(weight<=0)continue;
    let item=this.stroke?.get(i);if(this.stroke){if(!item){item={base:this.data.slice(i*4,i*4+4),coverage:0};this.stroke.set(i,item);}if(weight<=item.coverage)continue;item.coverage=weight;}
    const old=item?.base||this.data.slice(i*4,i*4+4);for(let k=0;k<4;k++){const target=rgb?(k===3?1:k===0?rgb.r:k===1?rgb.g:rgb.b):0;this.data[i*4+k]=old[k]*(1-weight)+target*weight;}this.compose(i);changed++;
   }
   for(let j=0;j<3;j++){const next=adj[f*3+j];if(next>=0&&!seen.has(next)){seen.add(next);queue.push(next);}}
  }if(changed)this.geometry.getAttribute('color').needsUpdate=true;return changed;
 }
 sample(face:number,point:T.Vector3){const p=this.geometry.getAttribute('position'),c=this.geometry.getAttribute('color'),v=new T.Vector3();let best=this.offsets[face],distance=Infinity;for(let i=best;i<this.offsets[face+1];i++){const d=v.fromBufferAttribute(p,i).distanceToSquared(point);if(d<distance){distance=d;best=i;}}return '#'+new T.Color(c.getX(best),c.getY(best),c.getZ(best)).getHexString();}
 material(scale:number){
  const material=new T.PointsMaterial({size:Math.max(.001,this.spacing*4.2*scale),sizeAttenuation:true,vertexColors:true,alphaTest:.15});
  material.onBeforeCompile=shader=>{
   shader.vertexShader='varying float roundShade;\n'+shader.vertexShader;
   shader.vertexShader=shader.vertexShader.replace('#include <begin_vertex>','#include <begin_vertex>\nroundShade=.68+.32*max(dot(normalize(normalMatrix*normal),normalize(vec3(-.35,.7,1.))),0.);');
   shader.fragmentShader='varying float roundShade;\n'+shader.fragmentShader;
   shader.fragmentShader=shader.fragmentShader.replace('#include <map_particle_fragment>','#include <map_particle_fragment>\nif(length(gl_PointCoord-vec2(.5))>.5)discard;diffuseColor.rgb*=roundShade;');
  };material.customProgramCacheKey=()=> 'scan3d-round-surface-v1';return material;
 }
 exportGeometry(){const g=this.geometry.clone();g.scale(.001,.001,.001);return g;}
}
