import assert from 'node:assert/strict';
import * as T from 'three';
import {DuckPaint} from '../src/DuckPaint.ts';
const create=()=>{
 const g=new T.BufferGeometry();g.setAttribute('position',new T.Float32BufferAttribute([0,0,0,10,0,0,0,10,0,10,10,0,0,0,.01,10,0,.01,0,10,.01],3));g.setIndex([0,1,2,1,3,2,4,5,6]);g.computeVertexNormals();
 const paint=new DuckPaint(g,new Uint8Array([0,1,2]),new Int32Array([1,-1,-1,0,-1,-1,-1,-1,-1]));paint.enableRoundSurface();return paint;
};
const p=create(),original=p.geometry.getAttribute('position').array.slice(),point=new T.Vector3(2,2,0);
p.begin();const count=p.smoothPaint(0,.5,'#ff0000',point,{style:'pen'});p.commit();
assert(count>50,'A circular dab must cover fine samples even inside a large triangle with no nearby vertices');
assert(p.surface.data.every(x=>x===0),'Round paint should not depend on coarse vertex coverage');
const dots=p.round,pos=dots.geometry.getAttribute('position');let total=0;
for(let i=0;i<dots.faceOf.length;i++)if(dots.data[i*4+3]>0){total++;assert.equal(dots.faceOf[i],0);assert(Math.hypot(pos.getX(i)-2,pos.getY(i)-2)<.501);}
assert.equal(total,count);assert.deepEqual(p.geometry.getAttribute('position').array,original);
const snapshot=p.snapshot();assert(p.undo());assert(p.round.data.every(x=>x===0));
p.restore(snapshot);assert.deepEqual(p.round.data,snapshot.round);
const restored=create();restored.restore(snapshot);assert.deepEqual(restored.round.data,p.round.data);assert.deepEqual(restored.round.geometry.getAttribute('position').array,pos.array);
p.clearPaint();assert(p.round.data.every(x=>x===0));assert(p.undo());assert.deepEqual(p.round.data,snapshot.round);
p.begin();p.smoothPaint(0,.5,null,point);p.commit();assert(p.round.data.some((x,i)=>i%4===3&&x<snapshot.round[i]));
assert.equal(p.round.exportGeometry().index,null);
console.log('PASS: circular footprint within coarse face, disconnected rear protection, immutable STL, erase, undo, clear, deterministic save/restore and point export');
