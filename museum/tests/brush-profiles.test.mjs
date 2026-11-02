import assert from 'node:assert/strict';
import * as T from 'three';
import {DuckPaint} from '../src/DuckPaint.ts';
import {brushWeight,BRUSHES} from '../src/BrushProfiles.ts';
const samples=BRUSHES.map(b=>[0,.25,.6,.9,1].map(t=>brushWeight(t,.12,.31,.29,{style:b.id})));
assert.equal(new Set(samples.map(JSON.stringify)).size,4,'Every brush must paint differently');
for(const b of BRUSHES){
 for(let i=0;i<=100;i++){const t=i/100,w=brushWeight(t,.12,.31,.29,{style:b.id});assert(w>=0&&w<=1);assert.equal(brushWeight(t,.12,.31,.29,{style:b.id,opacity:.5}),w*.5);}
 assert.equal(brushWeight(1,0,0,0,{style:b.id}),0);
}
assert.equal(brushWeight(.5,1,2,3,{style:'pencil'}),brushWeight(.5,1,2,3,{style:'pencil'}));
assert.equal(brushWeight(.98,0,0,0,{style:'pen'}),1,'Pen remains opaque up to its narrow edge');
assert(brushWeight(.5,0,0,0,{style:'pen',pressure:.1})>.86,'Light pen pressure still lays solid ink');
assert.equal(brushWeight(.5,0,0,0,{style:'pen',pressure:0}),0);
assert.notEqual(brushWeight(.5,1,2,3,{style:'pencil'}),brushWeight(.5,4,2,3,{style:'pencil'}));
for(const b of BRUSHES){
 const g=new T.BufferGeometry();g.setAttribute('position',new T.Float32BufferAttribute([0,0,0,1,0,0,0,1,0,0,0,.01,1,0,.01,0,1,.01],3));g.setIndex([0,1,2,3,4,5]);
 const p=new DuckPaint(g,new Uint8Array([0,1]),new Int32Array(6).fill(-1)),original=p.geometry.getAttribute('position').array.slice();
 const hit=new T.Vector3(.1,.1,0),settings={style:b.id};p.begin();p.smoothPaint(0,2,'#cc2020',hit,settings);const once=p.surface.data.slice();
 for(let i=0;i<20;i++)p.smoothPaint(0,2,'#cc2020',hit,settings);
 assert.deepEqual(p.surface.data,once,b.id+' is independent of event density');p.commit();
 assert(p.surface.data.slice(12).every(v=>v===0),'No disconnected back painting');
 p.begin();p.smoothPaint(0,2,'#20cc20',hit,settings);p.commit();assert(p.surface.data[3]>=once[3]);
 assert(p.undo());assert.deepEqual(p.surface.data,once);const saved=p.snapshot();p.clearPaint();p.restore(saved);assert.deepEqual(p.surface.data,once);
 assert.deepEqual(p.geometry.getAttribute('position').array,original);assert.deepEqual([...p.labels],[0,1]);
}
console.log('PASS: four distinct profiles, bounded falloff, opacity, stable pencil grain, stroke-density independence, layered strokes, rear protection, undo/save and unchanged geometry.');
