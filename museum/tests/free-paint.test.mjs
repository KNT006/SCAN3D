import assert from 'node:assert/strict';
import fs from 'node:fs';
import * as T from 'three';
import {DuckPaint} from '../src/DuckPaint.ts';
import {resolveSegmentation,paintKey} from '../src/museum/MuseumSegmentation.ts';
import {readArchive} from '../src/museum/MuseumArchive.ts';
import {defaults} from '../src/museum/MuseumData.ts';
import {zipSync,strToU8} from 'three/addons/libs/fflate.module.js';
const g=new T.BufferGeometry();g.setAttribute('position',new T.Float32BufferAttribute([0,0,0,1,0,0,0,1,0,1,1,0,0,0,.01,1,0,.01,0,1,.01],3));g.setIndex([0,1,2,1,3,2,4,5,6]);g.computeVertexNormals();
const p=new DuckPaint(g,new Uint8Array([0,0,0]),new Int32Array([1,-1,-1,0,-1,-1,-1,-1,-1]));
p.enableEdgeSmoothing(new T.MeshStandardMaterial({vertexColors:true}));
const original=p.geometry.getAttribute('position').array.slice();
p.begin();assert.equal(p.paintColor(0,.2,'#ff0000'),1);p.commit();
assert.deepEqual([...p.labels],[0,0,0]);assert.deepEqual([...p.faceColors],[0xff0000,-1,-1]);
assert.equal(p.edgeSmoothing.boundary[0],1);assert.equal(p.geometry.getAttribute('color').getX(0),1);
p.begin();p.paintColor(0,3,'#0000ff');p.commit();assert.deepEqual([...p.faceColors],[255,255,-1]); // disconnected rear surface untouched
assert(p.undo());assert.deepEqual([...p.faceColors],[0xff0000,-1,-1]);
p.begin();p.paintColor(0,.2,null);p.commit();assert.equal(p.faceColors[0],-1);p.undo();assert.equal(p.faceColors[0],0xff0000);
const saved=p.snapshot();p.clearPaint();assert(p.faceColors.every(x=>x===-1));p.undo();assert.equal(p.faceColors[0],0xff0000);
p.restore(saved);assert.deepEqual(p.faceColors,saved.faceColors);assert.deepEqual(p.geometry.getAttribute('position').array,original);
const output=p.exportGeometry();assert(output.getAttribute('color').array.some(x=>x===1));output.dispose();
const catalog=JSON.parse(fs.readFileSync(new URL('../public/museum/catalog.json',import.meta.url),'utf8'));
for(const base of catalog){
 const asset=resolveSegmentation(base);assert.equal(asset.segmentation_mode,'rgb');assert.equal(asset.labels_file,base.color_segmentation.labels_file);
 const paint=new Int32Array(asset.faces).fill(-1);paint[0]=0x123456;
 const manifest={format:'scan3d-exhibit',version:1,asset,record:defaults(asset),palette:asset.palette,softEdges:false};
 const pack=(extra={},raw=new Uint8Array(paint.buffer))=>new File([zipSync({'exhibit.json':strToU8(JSON.stringify({...manifest,...extra})),'face-regions.bin':new Uint8Array(asset.faces),'face-paint.bin':raw})],'test.zip');
 const result=await readArchive(pack(),catalog);assert.equal(paintKey(result.asset),paintKey(asset));assert.equal(result.paint.faceColors[0],0x123456);assert.equal(result.paint.softEdges,false);
 await assert.rejects(readArchive(pack({asset:{...asset,segmentation_mode:'cloud'}}),catalog),/照片辅助/);
 await assert.rejects(readArchive(pack({},new Uint8Array(2)),catalog),/长度/);
 const bad=new Int32Array(asset.faces).fill(-2);await assert.rejects(readArchive(pack({},new Uint8Array(bad.buffer)),catalog),/涂色数据无效/);
}
console.log('PASS: independent painting, disconnected-surface protection, erase/undo/clear, same-label smoothing, save/restore, GLB colors, photo-only archive and invalid paint rejection.');
