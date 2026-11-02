import * as T from 'three';
import {brushWeight} from './BrushProfiles.ts';
import type {BrushOptions} from './BrushProfiles.ts';

/** Independent premultiplied linear RGBA paint, interpolated over each triangle.
 * Shared source vertices receive identical strokes; disconnected surfaces do not.
 */
export class SurfaceBrush {
 data:Float32Array; copies:number[][]=[];vertexIds:number[];geometry:T.BufferGeometry;
 stroke:Map<number,{base:Float32Array;coverage:number}>|null=null;
 beginStroke(){this.stroke=new Map();}
 endStroke(){this.stroke=null;}
 constructor(geometry:T.BufferGeometry,index:number[]){
  this.geometry=geometry;this.vertexIds=index;this.data=new Float32Array(index.length*4);
  index.forEach((id,i)=>(this.copies[id]??=[]).push(i));
  geometry.setAttribute('surfacePaint',new T.BufferAttribute(this.data,4));
 }
 replace(data:Float32Array){this.data.set(data);this.dirty();}
 dirty(){this.geometry.getAttribute('surfacePaint').needsUpdate=true;}
 stamp(face:number,point:T.Vector3,radius:number,color:string|null,adj:Int32Array,options:BrushOptions={}){
  const pos=this.geometry.getAttribute('position'),tri=new T.Triangle(),closest=new T.Vector3();
  const queue=[face],seen=new Set(queue),vertices=new Set<number>();let changed=0;
  while(queue.length){const f=queue.pop()!;
   tri.a.fromBufferAttribute(pos,f*3);tri.b.fromBufferAttribute(pos,f*3+1);tri.c.fromBufferAttribute(pos,f*3+2);
   tri.closestPointToPoint(point,closest);if(closest.distanceToSquared(point)>radius*radius)continue;
   for(let k=0;k<3;k++)vertices.add(this.vertexIds[f*3+k]);
   for(let k=0;k<3;k++){const n=adj[f*3+k];if(n>=0&&!seen.has(n)){seen.add(n);queue.push(n);}}
  }
  const rgb=color===null?null:new T.Color(color),v=new T.Vector3();
  for(const id of vertices){const group=this.copies[id];v.fromBufferAttribute(pos,group[0]);
   const t=v.distanceTo(point)/radius;if(t>=1)continue;
   const w=brushWeight(t,v.x,v.y,v.z,color===null?{}:options);
   if(w<=0)continue;
   // Cover a vertex once per stroke. Mouse event density must not darken ink.
   let entry=this.stroke?.get(id);
   if(this.stroke){
    if(!entry){const o=group[0]*4;entry={base:this.data.slice(o,o+4),coverage:0};this.stroke.set(id,entry);}
    if(w<=entry.coverage)continue;entry.coverage=w;
   }
   for(const i of group){const offset=i*4;const old=this.data.slice(offset,offset+4);
    for(let k=0;k<4;k++){const target=rgb?(k===3?1:k===0?rgb.r:k===1?rgb.g:rgb.b):0;this.data[offset+k]=(entry?entry.base[k]:old[k])*(1-w)+target*w;}
    if(old.some((x,k)=>Math.abs(x-this.data[offset+k])>1e-6))changed++;
   }
  }
  if(changed)this.dirty();return changed;
 }
 sample(face:number,bary:number[]){const v=[0,0,0,0];for(let j=0;j<3;j++)for(let k=0;k<4;k++)v[k]+=this.data[(face*3+j)*4+k]*bary[j];return v;}
}
