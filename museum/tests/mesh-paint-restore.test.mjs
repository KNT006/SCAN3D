import assert from 'node:assert/strict';
import * as T from 'three';
import {DuckPaint} from '../src/DuckPaint.ts';
function fixture(){const g=new T.BufferGeometry();g.setAttribute('position',new T.Float32BufferAttribute([0,0,0,1,0,0,0,1,0,4,0,0,5,0,0,4,1,0],3));g.setIndex([0,1,2,3,4,5]);g.computeVertexNormals();return new DuckPaint(g,new Uint8Array(2),new Int32Array(6).fill(-1));}
const old=fixture();old.enableRoundSurface();
for(let i=old.round.offsets[0];i<old.round.offsets[1];i++)old.round.data.set([.6,.1,.2,.8],i*4);
const current=fixture();current.restore(old.snapshot());assert.equal(current.round,undefined);
for(let j=0;j<3;j++)for(let k=0;k<4;k++)assert(Math.abs(current.surface.data[j*4+k]-[.6,.1,.2,.8][k])<1e-4);
assert(current.surface.data.slice(12).every(x=>x===0),'no paint transferred to disconnected face');
const material=new T.MeshStandardMaterial({vertexColors:true});current.enableEdgeSmoothing(material);
const before=current.surface.data.slice();current.begin();current.smoothPaint(0,2,'#00ff00',new T.Vector3(.2,.2,0));current.commit();assert(current.undo());assert.deepEqual(current.surface.data,before);
const snapshot=current.snapshot();assert.equal(snapshot.round,undefined);const reload=fixture();reload.restore(snapshot);assert.deepEqual(reload.surface.data,before);
old.round.data.fill(0);current.restore(old.snapshot());assert(current.surface.data.every(x=>x===0),'erased round layer stays erased');
console.log('PASS: saved round paint migrates to mesh, disconnected faces stay separate, mesh brush undo and reload, erased paint remains erased');
