import assert from 'node:assert/strict';
import * as T from 'three';
import {DuckPaint} from '../src/DuckPaint.ts';

const g=new T.BufferGeometry();
g.setAttribute('position',new T.Float32BufferAttribute([0,0,0,1,0,0,0,1,0,1,1,0],3));
g.setIndex([0,1,2,1,3,2]);g.computeVertexNormals();
// Deliberately unordered neighbors; shared-edge matching must still work.
const p=new DuckPaint(g,new Uint8Array([0,1]),new Int32Array([1,-1,-1,-1,-1,0]));
p.palette=['#ff0000','#0000ff',...Array(6).fill('#ffffff')];
const m=new T.MeshStandardMaterial({vertexColors:true});p.enableEdgeSmoothing(m);
const edge=p.edgeSmoothing;assert(edge);
const original=p.geometry.getAttribute('position').array.slice(),labels=p.labels.slice();
const center=edge.sampleColor(0,[1/3,1/3,1/3]);assert.deepEqual(center,[1,0,0]);
const a=edge.sampleColor(0,[0,.5,.5]),b=edge.sampleColor(1,[.5,0,.5]);
assert.deepEqual(a,[.5,0,.5]);assert.deepEqual(a,b);
p.softEdges=false;p.refresh();assert.deepEqual(edge.sampleColor(0,[0,.5,.5]),[1,0,0]);
p.softEdges=true;p.refresh();
const exported=p.exportGeometry();exported.computeBoundingBox();
assert(Math.abs(exported.boundingBox.max.x-.001)<1e-9);assert(exported.getAttribute('position').count>6);
assert(Array.from(exported.getAttribute('position').array).every(Number.isFinite));
let area=0;const q=exported.getAttribute('position');
for(let i=0;i<q.count;i+=3){const x=new T.Vector3().fromBufferAttribute(q,i),y=new T.Vector3().fromBufferAttribute(q,i+1),z=new T.Vector3().fromBufferAttribute(q,i+2);area+=y.sub(x).cross(z.sub(x)).length()/2;}
assert(Math.abs(area-1e-6)<1e-12,'export subdivision must preserve area and winding coverage');
assert.deepEqual(p.geometry.getAttribute('position').array,original);assert.deepEqual(p.labels,labels);
p.highlight=true;p.refresh();assert.equal(edge.enabled.value,0);p.highlight=false;
p.labels[1]=7;p.refresh();assert.deepEqual(edge.sampleColor(0,[0,.5,.5]),[1,0,0],'never borrow a closing-cap color');
p.restore({softEdges:false});assert.equal(p.snapshot().softEdges,false);
exported.dispose();m.dispose();p.geometry.dispose();
console.log('PASS: shared-edge continuity, narrow protected interior, toggle, unknown isolation, export bounds/area, immutable geometry and labels, persistence.');
