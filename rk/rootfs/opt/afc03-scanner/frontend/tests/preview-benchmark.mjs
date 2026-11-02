// CPU-side comparison of the old cloning/geometry-conversion path and new
// append/update path. Not a GPU frame-rate measurement.
import * as T from 'three';
import {PreviewBuffer} from '../src/previewBuffer.ts';
const lut=Float32Array.from({length:256},(_,i)=>new T.Color().setRGB(i/255,i/255,i/255,T.SRGBColorSpace).r);
function run(old){
 global.gc?.();const base=process.memoryUsage().heapUsed;let peak=base,points=[],colors=[],times=[];
 const buffer=new PreviewBuffer(),linear=new Float32Array(160000*3);
 for(let batch=0;batch<400;batch++){
  const t=performance.now();
  if(old){
   for(let k=0;k<8000;k++){points.push([batch*8+Math.floor(k/1000),k%1000,0]);colors.push([123,80,220])}
   points=points.slice();colors=colors.slice();if(points.length>160000){points=points.filter((_,i)=>i%2===0);colors=colors.filter((_,i)=>i%2===0)}
   const g=new T.BufferGeometry();g.setAttribute('position',new T.Float32BufferAttribute(points.flat(),3));
   const c=[],v=new T.Color();for(const rgb of colors){v.setRGB(rgb[0]/255,rgb[1]/255,rgb[2]/255,T.SRGBColorSpace);c.push(v.r,v.g,v.b)}
   g.setAttribute('color',new T.Float32BufferAttribute(c,3));g.computeBoundingBox();g.dispose();
  }else{
   const start=buffer.count*3;
   for(let j=0;j<8;j++)buffer.append({index:batch*8+j,xyz:Array.from({length:50},(_,k)=>[batch*8+j,k,0]),rgb:Array.from({length:50},()=>[123,80,220])});
   for(let k=start;k<buffer.count*3;k++)linear[k]=lut[buffer.rgb[k]];
  }
  times.push(performance.now()-t);peak=Math.max(peak,process.memoryUsage().heapUsed);
 }
 times.sort((a,b)=>a-b);
 return {path:old?'old':'new',p50_ms:times[200],p95_ms:times[380],peak_heap_delta:peak-base,points:old?points.length:buffer.count,first_position_points:old?points.filter(p=>p[0]===0).length:50,typed_bytes:old?null:buffer.xyz.byteLength+buffer.rgb.byteLength+linear.byteLength};
}
console.log(JSON.stringify([run(true),run(false)],null,2));
