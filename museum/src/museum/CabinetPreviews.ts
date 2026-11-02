import * as T from 'three';
import {DuckPaint,loadPaint} from '../DuckPaint';
import {loadAsset} from './MuseumAssets';
import {paintKey} from './MuseumSegmentation';
import type {ExhibitAsset,ExhibitRecord} from './MuseumData';
import {cachedPreview,savePreview,previewSignature} from './CabinetCache';

/** Render actual meshes, one at a time, with saved user colors. No gallery animation loop. */
export async function renderCabinetPreviews(
 assets:ExhibitAsset[], records:Record<string,ExhibitRecord>, signal:AbortSignal,
 publish:(id:string,url:string)=>void,
){
 let renderer:T.WebGLRenderer|undefined;
 try{
  const pending:{asset:ExhibitAsset;signature:string}[]=[];
  await Promise.all(assets.map(async asset=>{const signature=previewSignature(asset,records[asset.id]?.yaw||0),blob=await cachedPreview(asset.id,signature);if(signal.aborted)return;if(blob)publish(asset.id,URL.createObjectURL(blob));else pending.push({asset,signature});}));
  if(signal.aborted||!pending.length)return;
  // Imported entries have placeholder thumbnails; draw them before built-in previews.
  pending.sort((a,b)=>Number(b.asset.id.startsWith('scan-'))-Number(a.asset.id.startsWith('scan-'))||a.asset.faces-b.asset.faces);
  renderer=new T.WebGLRenderer({antialias:true,alpha:true,powerPreference:'low-power'});
  renderer.setSize(640,440);renderer.setPixelRatio(1);
  renderer.outputColorSpace=T.SRGBColorSpace;renderer.toneMapping=T.ACESFilmicToneMapping;
  renderer.toneMappingExposure=1.05;
  for(const {asset,signature} of pending){
   if(signal.aborted)break;
   let paint:DuckPaint|undefined,material:T.MeshStandardMaterial|undefined;
   try{
    const data=await loadAsset(asset,signal);
    if(signal.aborted){data.geometry.dispose();break;}
    paint=new DuckPaint(data.geometry,data.labels,data.adj);
    paint.palette=[...asset.palette];paint.refresh();
    try{const saved=await loadPaint(paintKey(asset));if(saved)paint.restore(saved);}catch{/* Default palette is a valid fallback. */}
    if(signal.aborted)break;
    const scene=new T.Scene();
    scene.add(new T.HemisphereLight('#fff9ef','#b2c5c6',1.5));
    const key=new T.DirectionalLight('#fff5e5',2.3);key.position.set(-3,6,5);scene.add(key);
    const rim=new T.DirectionalLight('#e8f5f5',1);rim.position.set(4,3,-3);scene.add(rim);
    // Cabinet thumbnails only need baked vertex colors, not editable edge-neighbor shaders.
    const colors=paint.geometry.getAttribute('color').array as Float32Array,layer=paint.surface.data;
    for(let i=0;i<layer.length/4;i++)for(let k=0;k<3;k++)colors[i*3+k]=colors[i*3+k]*(1-layer[i*4+3])+layer[i*4+k];
    material=new T.MeshStandardMaterial({vertexColors:true,roughness:.72,metalness:0,side:T.DoubleSide});
    const mesh=new T.Mesh(paint.geometry,material);
    mesh.rotation.y=(records[asset.id]?.yaw||0)*Math.PI/180;scene.add(mesh);mesh.updateMatrixWorld();
    const box=new T.Box3().setFromObject(mesh),center=box.getCenter(new T.Vector3());
    const camera=new T.OrthographicCamera(-1,1,1,-1,.1,1000);
    camera.position.copy(center).add(new T.Vector3(4.1,2.25,6.1).normalize().multiplyScalar(250));
    camera.lookAt(center);camera.updateMatrixWorld();
    const projected=new T.Box3(),point=new T.Vector3(),positions=paint.geometry.getAttribute('position');
    const transform=new T.Matrix4().multiplyMatrices(camera.matrixWorldInverse,mesh.matrixWorld);
    for(let i=0;i<positions.count;i++)projected.expandByPoint(point.fromBufferAttribute(positions,i).applyMatrix4(transform));
    const size=projected.getSize(new T.Vector3()),mid=projected.getCenter(new T.Vector3());
    const half=Math.max(size.y,size.x/(640/440))*.53;
    camera.left=mid.x-half*640/440;camera.right=mid.x+half*640/440;camera.top=mid.y+half;camera.bottom=mid.y-half;
    camera.updateProjectionMatrix();renderer.render(scene,camera);
    const blob=await new Promise<Blob|null>(resolve=>renderer!.domElement.toBlob(resolve,'image/png'));
    if(blob&&!signal.aborted){publish(asset.id,URL.createObjectURL(blob));await savePreview(asset.id,signature,blob);}
   }catch(e){if(!signal.aborted)console.warn('Cabinet preview fallback:',asset.id,e);}
   finally{paint?.geometry.dispose();material?.dispose();}
   await new Promise(resolve=>setTimeout(resolve,0));
  }
 }finally{renderer?.dispose();renderer?.forceContextLoss();}
}
