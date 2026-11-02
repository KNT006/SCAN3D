import * as T from 'three';
import type {ExhibitAsset} from './MuseumData';
export async function loadAsset(a:ExhibitAsset,signal:AbortSignal){
 const start=performance.now();const names=['vertices.bin','faces.bin',a.labels_file||'face-regions.bin','face-adjacency.bin'];
 const b=await Promise.all(names.map(async n=>{const r=await fetch(a.asset_base+n,{signal});if(!r.ok)throw Error(n+' 加载失败 '+r.status);return r.arrayBuffer();}));
 if(b[0].byteLength!==a.vertices*12||b[1].byteLength!==a.faces*12||b[2].byteLength!==a.faces||b[3].byteLength!==a.faces*12)throw Error('模型数据长度不匹配');
 const v=new Float32Array(b[0]),f=new Uint32Array(b[1]),labels=new Uint8Array(b[2]),adj=new Int32Array(b[3]);
 if(!v.every(Number.isFinite)||!f.every(i=>i<a.vertices)||!labels.every(i=>i<8)||!adj.every(i=>i>=-1&&i<a.faces))throw Error('模型数据无效');
 const geometry=new T.BufferGeometry();geometry.setAttribute('position',new T.BufferAttribute(v,3));geometry.setIndex(new T.BufferAttribute(f,1));geometry.computeVertexNormals();
 return {geometry,labels,adj,buffers:b,ms:performance.now()-start};
}
