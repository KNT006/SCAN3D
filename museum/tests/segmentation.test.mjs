import assert from 'node:assert/strict';import fs from 'node:fs';
import {resolveSegmentation,paintKey} from '../src/museum/MuseumSegmentation.ts';
const catalog=JSON.parse(fs.readFileSync(new URL('../public/museum/catalog.json',import.meta.url),'utf8'));
for(const a of catalog){const s=resolveSegmentation(a);assert.equal(s.segmentation_mode,'rgb');assert.equal(s.geometry_key,a.geometry_key);assert.equal(paintKey(s),a.geometry_key+':'+a.color_segmentation.version);assert.equal(s.labels_file,a.color_segmentation.labels_file);}
assert.throws(()=>resolveSegmentation({id:'missing'}),/缺少照片辅助/);
console.log('PASS: photo-only regions, paint identity preserved, missing regions rejected.');
