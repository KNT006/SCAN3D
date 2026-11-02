import assert from 'node:assert/strict';
import * as T from 'three';
import {DuckPaint} from '../src/DuckPaint.ts';
import {DuckInteraction} from '../src/DuckInteraction.ts';
const geometry=new T.PlaneGeometry(2,2),paint=new DuckPaint(geometry,new Uint8Array([0,1]),new Int32Array([1,-1,-1,0,-1,-1]));
paint.palette[0]='#AbCdEf';paint.palette[1]='#123456';paint.refresh();
assert.equal(paint.colorAt(0),'#abcdef');
paint.begin();paint.paintColor(0,.1,'#0080ff');paint.commit();
const before=paint.snapshot(),undoCount=paint.history.length;
paint.highlight=true;paint.neutral=true;paint.refresh();assert.equal(paint.colorAt(0),'#0080ff');assert.equal(paint.colorAt(1),'#123456');
for(const bad of [-1,2,NaN,1.5])assert.equal(paint.colorAt(bad),null);
assert.deepEqual(paint.snapshot(),before);assert.equal(paint.history.length,undoCount);
class Canvas extends EventTarget {getBoundingClientRect(){return{left:0,top:0,width:200,height:200};}}
const el=new Canvas(),camera=new T.PerspectiveCamera(40,1,.1,50);camera.position.z=5;camera.updateMatrixWorld();
const root=new T.Group();root.add(new T.Mesh(paint.geometry,new T.MeshBasicMaterial()));root.updateMatrixWorld(true);
const events=[],interaction=new DuckInteraction(el,camera,root,new T.Group(),(name,p)=>events.push({name,p}));interaction.paintMode='eyedropper';
function pointer(type,x,y,button=0){const e=new Event(type);Object.assign(e,{clientX:x,clientY:y,button,pointerId:1});el.dispatchEvent(e);}
pointer('pointerdown',95,95);pointer('pointerup',95,95);assert.equal(events.length,1);assert.equal(events[0].name,'paint:sample');assert(Number.isInteger(events[0].p.face));
events.length=0;pointer('pointerdown',95,95);pointer('pointerup',130,100);assert.equal(events.length,0);
pointer('pointerdown',1,1);pointer('pointerup',1,1);assert.equal(events.length,0);
pointer('pointerdown',95,95,2);pointer('pointerup',95,95,2);assert.equal(events.length,0);
interaction.dispose();pointer('pointerdown',95,95);pointer('pointerup',95,95);assert.equal(events.length,0);paint.geometry.dispose();
console.log('PASS: underlying region and painted color sampling, ignore lights/highlight, invalid hits, no mutation, click-vs-drag, background/right button, listener cleanup.');
